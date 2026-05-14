import logging
from typing import Optional
from aptly_api import Client
from aptly_api.parts.publish import PublishEndpoint
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException
from packtly_builder_tooling.parts.hostarch import get_architecture

logger = logging.getLogger(__name__)


class Aptly:
    def __init__(self, host: Optional[str]) -> None:
        if host is None:
            raise ValueError("No hostname is set")
        version = None
        try:
            self.client = Client(host, http_auth=HTTPBasicAuth("admin", "kaffee"))

            version = self.client.misc.version()
        except RequestException as e:
            raise e

        if self.client is not None:
            logger.info(
                "Connection to %s with version %s is established", host, version
            )
        else:
            logger.error("No connection to aptly server")

    def get_publish_endpoint(
        self, distribution: str, component: str
    ) -> Optional[PublishEndpoint]:
        arch = get_architecture()
        aptly_dist_list = list(
            filter(
                lambda x: x.distribution == distribution and arch in x.architectures,
                self.client.publish.list(),
            )
        )

        for endpoint in aptly_dist_list:
            for source in endpoint.sources:
                if component == source["Component"]:
                    return endpoint
        return None

    def log_publish_endpoints(self) -> None:
        for endpoint in self.client.publish.list():
            logger.info("%s", "=" * 40)
            logger.info("Distribution: %s", endpoint.distribution)
            logger.info("%s", "=" * 40)

            # Log each field
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

    def upload_deb_files(
        self,
        endpoint: PublishEndpoint,
        name: str,
        files: list,
        keyid: str,
        passphrase: str,
        component: str = "",
    ) -> bool:

        logger.info("Attempting to upload at aptly server at %s", self.client.host)
        logger.info("Attempting to upload files: %s", files)

        repo_name = None

        repo_name = None
        for source in endpoint.sources:
            if source.get("Component") == component:
                repo_name = source.get("Name")
                break

        if not repo_name:
            logger.error(
                "Component '%s' not found in endpoint sources: %s",
                component,
                endpoint.sources,
            )
            return False
        try:
            filesapi = self.client.files
            reposapi = self.client.repos
            publishapi = self.client.publish

            # Upload the .deb files
            filesapi.upload(name, *files)

            # Add the uploaded files to the repository
            reposapi.add_uploaded_file(repo_name, name, force_replace=True)

            publishapi.update(
                prefix=".",
                distribution=endpoint.distribution,
                sign_batch=True,
                force_overwrite=True,
                sign_gpgkey=keyid,
                sign_passphrase=passphrase,
            )
            return True
        except RequestException as e:
            logger.error("Failed to upload packages: %s", e)
            return False
