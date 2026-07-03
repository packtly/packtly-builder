import logging
import os
from typing import Optional

from aptly_api import Client
from aptly_api.base import AptlyAPIException
from aptly_api.parts.publish import PublishEndpoint
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

from packtly_builder_tooling.parts.hostarch import (
    get_architecture,
)

logger = logging.getLogger(__name__)


class Aptly:
    def __init__(
        self,
        host: Optional[str],
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        if host is None:
            raise ValueError("No hostname is set")
        self.host = host
        try:
            http_auth = (
                HTTPBasicAuth(username, password) if username and password else None
            )

            self.client = Client(
                host,
                http_auth=http_auth,
            )

            version = self.client.misc.version()

            logger.info(
                "Connection to %s with version %s established",
                host,
                version,
            )

        except (
            RequestException,
            AptlyAPIException,
        ) as e:
            raise ConnectionError(f"Could not reach aptly server at {host}") from e

    def get_publish_endpoint(
        self,
        distribution: str,
        component: str,
    ) -> Optional[PublishEndpoint]:

        arch = get_architecture()

        try:
            endpoints = list(
                filter(
                    lambda x: (
                        x.distribution == distribution and arch in x.architectures
                    ),
                    self.client.publish.list(),
                )
            )

        except RequestException as e:
            logger.error(
                "Failed to list publish endpoints: %s",
                e,
            )
            return None

        for endpoint in endpoints:
            for source in endpoint.sources:
                if source["Component"] == component:
                    return endpoint

        return None

    def find_repo_name(
        self,
        endpoint: PublishEndpoint,
        component: str,
    ) -> Optional[str]:

        for source in endpoint.sources:
            if source.get("Component") == component:
                return source.get("Name")

        return None

    def package_exists(
        self,
        repo_name: str,
        package_key: str,
    ) -> bool:
        """
        package_key example:
        Pmypackage_1.0.0_amd64
        """

        try:
            packages = self.client.repos.search_packages(
                repo_name,
                detailed=True,
            )

            for package in packages:
                if package.key == package_key:
                    logger.info(
                        "Package already exists: %s",
                        package_key,
                    )
                    return True

            return False

        except (
            RequestException,
            AptlyAPIException,
        ) as e:
            logger.error(
                "Failed package lookup: %s",
                e,
            )
            return False

    def upload_deb_files(
        self,
        endpoint: PublishEndpoint,
        name: str,
        files: list[str],
        keyid: str,
        passphrase: str,
        component: str = "",
        force_upload: bool = False,
    ) -> bool:

        logger.info(
            "Uploading to aptly server at %s",
            self.host,
        )

        repo_name = self.find_repo_name(
            endpoint,
            component,
        )

        if not repo_name:
            logger.error(
                "Component '%s' not found",
                component,
            )
            return False

        try:
            filesapi = self.client.files
            reposapi = self.client.repos
            publishapi = self.client.publish

            changed = False

            for file in files:
                filename = os.path.basename(file)

                logger.info(
                    "Uploading candidate: %s",
                    filename,
                )

                uploaded = filesapi.upload(
                    name,
                    file,
                )

                if not uploaded:
                    logger.error(
                        "Upload failed for %s",
                        filename,
                    )
                    return False

            uploaded_packages = reposapi.add_uploaded_file(
                repo_name,
                name,
                remove_processed_files=True,
                force_replace=force_upload,
            )

            if uploaded_packages.failed_files:
                logger.error(
                    "Failed adding package: %s",
                    uploaded_packages.failed_files,
                )
                logger.error(
                    "Failed adding package report: %s",
                    uploaded_packages.report.get("Warnings", []),
                )
                return False

            added_keys = set(uploaded_packages.report.get("Added", []))

            if force_upload:
                changed = True

            elif not added_keys:
                logger.info("No new packages were added")

            else:
                changed = True

            if not changed:
                logger.info("No repository changes detected")
                return True

            publishapi.update(
                prefix=endpoint.prefix,
                distribution=endpoint.distribution,
                sign_batch=True,
                force_overwrite=force_upload,
                sign_gpgkey=keyid,
                sign_passphrase=passphrase,
            )

            logger.info(
                "Published distribution '%s'",
                endpoint.distribution,
            )

            return True

        except (
            RequestException,
            AptlyAPIException,
        ) as e:
            logger.error(
                "Failed to upload packages: %s",
                e,
            )
            return False

    def log_publish_endpoints(self) -> None:
        for endpoint in self.client.publish.list():
            logger.info("%s", "=" * 40)
            logger.info("Distribution: %s", endpoint.distribution)
            logger.info("%s", "=" * 40)

            logger.info("Storage: %s", endpoint.storage)
            logger.info("Prefix: %s", endpoint.prefix)
            logger.info("Source Kind: %s", endpoint.source_kind)
            logger.info("Label: %s", endpoint.label)
            logger.info("Origin: %s", endpoint.origin)
            logger.info("Acquire by Hash: %s", endpoint.acquire_by_hash)

            logger.info("Sources:")
            for source in endpoint.sources:
                logger.info("  - Component: %s", source["Component"])
                logger.info("    Name: %s", source["Name"])

            logger.info(
                "Architectures Supported: %s", ", ".join(endpoint.architectures)
            )

    def log_repos(self) -> None:
        for repo in self.client.repos.list():
            logger.info("%s", "=" * 40)
            logger.info("Repo Name: %s", repo.name)
            logger.info("Comment: %s", repo.comment)
            logger.info("Default Distribution: %s", repo.default_distribution)
            logger.info("Default Component: %s", repo.default_component)
            logger.info("%s", "=" * 40)
