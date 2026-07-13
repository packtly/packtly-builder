*** Settings ***
Library     OperatingSystem
Library     Process
Resource    ../keywords/git.robot
Resource    ../keywords/gpg.robot
Resource    ../keywords/aptly.robot

Suite Setup       Prepare Workspace
Suite Teardown    Run Keyword If    '${WORKSPACE}' != ''    Remove Directory    ${WORKSPACE}    recursive=True


*** Variables ***
${FIXTURES_DIR}         ${CURDIR}/../../fixtures
${DEBHELLO_DIR}         ${FIXTURES_DIR}/debhello-quilt
${CONTAINER_IMAGE}      packtly-builder:latest
${DEBIAN_IMAGE}          debian:trixie
${APTLY_CREDENTIALS}    ${EMPTY}
${WORKSPACE}            ${EMPTY}
${KEYS_DIR}             ${EMPTY}

*** Keywords ***
Prepare Workspace
    Set Suite Variable    ${WORKSPACE}    ${TEMPDIR}/debhello-quilt-build
    Set Suite Variable    ${KEYS_DIR}    ${WORKSPACE}/keys
    Set Suite Variable    ${APTLY_CREDENTIALS}    ${WORKSPACE}/aptly-credentials
    Run Process    git    clean    -fdx    cwd=${FIXTURES_DIR}
    Create Directory    ${WORKSPACE}
    Create Directory    ${WORKSPACE}/logs
    Generate GPG Keys    ${KEYS_DIR}    ${CONTAINER_IMAGE}
    Generate Aptly Credentials    ${APTLY_CREDENTIALS}

Run Debhello Quilt Build
    [Arguments]
    ...    ${workspace}
    ...    ${keys_dir}
    ...    ${aptly_credentials}
    ...    ${image}
    ...    ${dist}=trixie-apollo
    ...    ${component}=main

    ${result}=    Run Process
    ...    podman    run    --rm
    ...    -v    ${workspace}:/workspace:Z
    ...    -v    ${keys_dir}/public/repo_signing.key:/opt/keys/gpg/repo_signing.key:Z,ro
    ...    -v    ${keys_dir}/private/repo_signing_private.key:/opt/keys/gpg/repo_signing_private.key:Z,ro
    ...    -v    ${keys_dir}/private/repo_signing_private_pass:/opt/keys/gpg/repo_signing_private_pass:Z,ro
    ...    -v    ${aptly_credentials}:/run/secrets/aptly-credentials:Z,ro
    ...    -v    ${workspace}/logs:/logs:Z
    ...    -e    APTLYHOST\=http://localhost:8080
    ...    --network\=host
    ...    ${image}
    ...    /workspace/debhello-quilt
    ...    --log-file    /logs/build.log
    ...    --dist    ${dist}
    ...    --component    ${component}
    ...    --build-mode    full

    Log File    ${workspace}/logs/build.log
    Copy File    ${workspace}/logs/build.log    ${CURDIR}/../results/debhello_build.log
    Should Be Equal As Integers    ${result.rc}    0
    ...    Build failed with rc ${result.rc}. See stdout/stderr and build.log above.

Verify Build Artifacts
    [Documentation]    Verify a successful build produced valid .changes and .deb artifacts.
    [Arguments]    ${workspace}    ${image}

    # A successful debuild leaves the .changes and .deb files in the workspace.
    ${changes}=    List Files In Directory    ${workspace}    *.changes    absolute=True
    Should Not Be Empty    ${changes}    No .changes file produced - build did not complete
    ${debs}=    List Files In Directory    ${workspace}    *.deb    absolute=True
    Should Not Be Empty    ${debs}    No .deb packages produced

    # Validate each .deb is a structurally valid Debian package.
    FOR    ${deb}    IN    @{debs}
        ${info}=    Run Process
        ...    podman    run    --rm
        ...    --entrypoint    dpkg-deb
        ...    -v    ${workspace}:/workspace:Z,ro
        ...    ${image}
        ...    --info    /workspace/${deb.rsplit('/', 1)[1]}
        Log    ${info.stdout}
        Should Be Equal As Integers    ${info.rc}    0
        ...    dpkg-deb rejected ${deb}: ${info.stderr}
    END

Verify Changes Signature
    [Arguments]    ${workspace}    ${keys_dir}    ${image}

    ${changes}=    List Files In Directory    ${workspace}    *.changes    absolute=True
    Length Should Be    ${changes}    1

    ${changes_file}=    Set Variable    ${changes[0].rsplit('/',1)[1]}
    ${cmd}=    Set Variable
    ...    gpg --batch --import /tmp/repo_signing.key >/dev/null 2>&1 && gpg --status-fd\=1 --verify /workspace/${changes_file}
    ${result}=    Run Process
    ...    podman    run    --rm
    ...    -v    ${workspace}:/workspace:Z,ro
    ...    -v    ${keys_dir}/public/repo_signing.key:/tmp/repo_signing.key:Z,ro
    ...    --entrypoint    sh
    ...    ${image}
    ...    -c    ${cmd}

    Log    ${result.stdout}
    Log    ${result.stderr}

    Should Be Equal As Integers    ${result.rc}    0    GPG verification failed! Check logs.
    Should Contain    ${result.stdout}    [GNUPG:] GOODSIG
    Should Contain    ${result.stdout}    [GNUPG:] VALIDSIG

Verify Package Is Installable
    [Documentation]    Verify each produced .deb can be installed with dpkg inside the build container.
    [Arguments]    ${workspace}    ${image}

    ${debs}=    List Files In Directory    ${workspace}    *.deb    absolute=True
    Should Not Be Empty    ${debs}    No .deb packages found to install

    FOR    ${deb}    IN    @{debs}
        ${deb_name}=    Set Variable    ${deb.rsplit('/', 1)[1]}
        ${result}=    Run Process
        ...    podman    run    --rm
        ...    --entrypoint    sh
        ...    -v    ${workspace}:/workspace:Z,ro
        ...    ${image}
        ...    -c    dpkg --install --force-depends /workspace/${deb_name}
        Log    ${result.stdout}
        Log    ${result.stderr}
        Should Be Equal As Integers    ${result.rc}    0
        ...    dpkg --install failed for ${deb_name}: ${result.stderr}
    END

Verify Source Package Artifacts
    [Documentation]    Verify source package artifacts (.dsc + referenced tarballs) exist and pass dpkg-source integrity check.
    [Arguments]    ${workspace}    ${image}

    ${dscs}=    List Files In Directory    ${workspace}    *.dsc    absolute=True
    Should Not Be Empty    ${dscs}    No .dsc file produced - source package missing

    ${dsc_file}=    Set Variable    ${dscs[0].rsplit('/', 1)[1]}
    ${result}=    Run Process
    ...    podman    run    --rm
    ...    --entrypoint    sh
    ...    -v    ${workspace}:/workspace:Z,ro
    ...    ${image}
    ...    -c    command -v dpkg-source || apt-get update -qq && apt-get install -y --no-install-recommends dpkg-dev && dpkg-source -x /workspace/${dsc_file} /tmp/src-check && rm -rf /tmp/src-check

    Log    ${result.stdout}
    Log    ${result.stderr}
    Should Be Equal As Integers    ${result.rc}    0
    ...    dpkg-source -x failed for ${dsc_file}: ${result.stderr}

Verify DSC Signature
    [Arguments]    ${workspace}    ${keys_dir}    ${image}

    ${dscs}=    List Files In Directory    ${workspace}    *.dsc    absolute=True
    Length Should Be    ${dscs}    1

    ${dsc_file}=    Set Variable    ${dscs[0].rsplit('/', 1)[1]}
    ${cmd}=    Set Variable
    ...    gpg --batch --import /tmp/repo_signing.key >/dev/null 2>&1 && gpg --status-fd\=1 --verify /workspace/${dsc_file}
    ${result}=    Run Process
    ...    podman    run    --rm
    ...    -v    ${workspace}:/workspace:Z,ro
    ...    -v    ${keys_dir}/public/repo_signing.key:/tmp/repo_signing.key:Z,ro
    ...    --entrypoint    sh
    ...    ${image}
    ...    -c    ${cmd}

    Log    ${result.stdout}
    Log    ${result.stderr}

    Should Be Equal As Integers    ${result.rc}    0    GPG verification of .dsc failed! Check logs.
    Should Contain    ${result.stdout}    [GNUPG:] GOODSIG
    Should Contain    ${result.stdout}    [GNUPG:] VALIDSIG


*** Test Cases ***

Debhello Quilt Build
    [Documentation]    Test building debhello package with packtly-builder
    [Tags]    debhello    build
    Copy Directory    ${FIXTURES_DIR}/debhello-quilt    ${WORKSPACE}/debhello-quilt
    Run Debhello Quilt Build
    ...    ${WORKSPACE}
    ...    ${KEYS_DIR}
    ...    ${APTLY_CREDENTIALS}
    ...    image=${CONTAINER_IMAGE}

Binary Packages Are Valid
    [Documentation]    Verify .changes and .deb artifacts were produced and are structurally valid.
    [Tags]    debhello    build    binary
    Verify Build Artifacts    ${WORKSPACE}    ${CONTAINER_IMAGE}

Changes File Is Signed
    [Documentation]    Verify the .changes file carries a valid GPG signature.
    [Tags]    debhello    build    signature
    Verify Changes Signature    ${WORKSPACE}    ${KEYS_DIR}    ${CONTAINER_IMAGE}

Binary Package Is Installable
    [Documentation]    Verify each produced .deb can be installed with dpkg on a clean Debian image.
    [Tags]    debhello    install    binary
    Verify Package Is Installable    ${WORKSPACE}    ${DEBIAN_IMAGE}

Source Package Is Valid
    [Documentation]    Verify the .dsc and referenced source tarballs pass dpkg-source integrity check.
    [Tags]    debhello    build    source
    Verify Source Package Artifacts    ${WORKSPACE}    ${CONTAINER_IMAGE}

DSC File Is Signed
    [Documentation]    Verify the .dsc file carries a valid GPG signature.
    [Tags]    debhello    build    signature    source
    Verify DSC Signature    ${WORKSPACE}    ${KEYS_DIR}    ${CONTAINER_IMAGE}

Source Package Is Installable
    [Documentation]    Verify the source package (.dsc + tarballs) can be extracted by dpkg-source on a clean Debian image.
    [Tags]    debhello    install    source
    Verify Source Package Artifacts    ${WORKSPACE}    ${DEBIAN_IMAGE}
