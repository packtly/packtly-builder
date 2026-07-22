*** Settings ***
Documentation    Keywords for generating Aptly credentials used in integration tests.
Library    OperatingSystem
Library    Process
Library    String


*** Keywords ***
Create Packtly Data Volume
    [Documentation]    Create the external Podman volume used by the Packtly Infra container.
    [Arguments]    ${volume}
    Run Process    podman    volume    rm    --force    ${volume}
    ${result}=    Run Process    podman    volume    create    ${volume}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Remove Packtly Data Volume
    [Documentation]    Remove the Podman volume created for this test suite.
    [Arguments]    ${volume}
    Run Process    podman    volume    rm    --force    ${volume}

Generate Aptly Credentials
    [Documentation]    Generate a simple aptly credentials file
    [Arguments]    ${path}
    ...    ${username}=admin
    ...    ${password}=password

    Create File    ${path}    username=${username}\npassword=${password}

Generate Packtly Htpasswd
    [Documentation]    Generate a Packtly basic-auth file using the Packtly Compose service.
    [Arguments]    ${compose_file}
    ...    ${project_name}
    ...    ${username}=admin
    ...    ${password}=password

    ${result}=    Run Process
    ...    podman-compose
    ...    --file    ${compose_file}
    ...    --project-name    ${project_name}
    ...    run    --no-deps    --rm    -T
    ...    --entrypoint    /usr/local/bin/gen_htpasswd
    ...    packtly
    ...    ${username}
    ...    ${password}
    Log    ${result.stdout}
    Log    ${result.stderr}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Get Podman Volume Mountpoint
    [Documentation]    Return the host mountpoint of a Podman volume.
    [Arguments]    ${volume}

    ${result}=    Run Process
    ...    podman    volume    inspect
    ...    --format    {{.Mountpoint}}
    ...    ${volume}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}
    ${mountpoint}=    Strip String    ${result.stdout}
    RETURN    ${mountpoint}

Install Packtly Public Files
    [Documentation]    Copy the GPG public signing key directly into the Packtly data volume's mountpoint.
    ...    The infra service reads it from /opt/packtly/public/repo_signing.key.
    [Arguments]    ${volume}    ${public_key}

    ${mountpoint}=    Get Podman Volume Mountpoint    ${volume}
    Create Directory    ${mountpoint}/public
    Copy File    ${public_key}    ${mountpoint}/public/repo_signing.key

Import Podman Secret
    [Documentation]    Replace a Podman secret with the contents of ${secret_file}.
    [Arguments]    ${secret_name}    ${secret_file}

    Run Process    podman    secret    rm    --ignore    ${secret_name}
    ${result}=    Run Process
    ...    podman    secret    create
    ...    ${secret_name}
    ...    ${secret_file}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Remove Podman Secret
    [Documentation]    Remove a Podman secret.
    [Arguments]    ${secret_name}

    Run Process    podman    secret    rm    --ignore    ${secret_name}

Start Podman Compose Service
    [Documentation]    Start services from ${compose_file} in the background.
    [Arguments]    ${compose_file}    ${project_name}

    ${result}=    Run Process
    ...    podman-compose
    ...    --file    ${compose_file}
    ...    --project-name    ${project_name}
    ...    up    --detach
    Log    ${result.stdout}
    Log    ${result.stderr}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Stop Podman Compose Service
    [Documentation]    Stop services from ${compose_file} without removing external resources.
    [Arguments]    ${compose_file}    ${project_name}

    Run Process
    ...    podman-compose
    ...    --file    ${compose_file}
    ...    --project-name    ${project_name}
    ...    down

Exec In Packtly Service
    [Documentation]    Execute a command inside the running Packtly Infra service container.
    [Arguments]    ${compose_file}    ${project_name}    @{command}

    ${result}=    Run Process
    ...    podman-compose
    ...    --file    ${compose_file}
    ...    --project-name    ${project_name}
    ...    exec    -T    packtly    @{command}
    Log    ${result.stdout}
    Log    ${result.stderr}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Wait Until Packtly Service Ready
    [Documentation]    Wait until the Packtly Infra service accepts exec calls.
    [Arguments]    ${compose_file}    ${project_name}    ${timeout}=30s    ${retry_interval}=2s

    Wait Until Keyword Succeeds    ${timeout}    ${retry_interval}
    ...    Exec In Packtly Service    ${compose_file}    ${project_name}    true

Import Packtly GPG Key
    [Documentation]    Import the GPG signing key into the running Packtly Infra service.
    [Arguments]    ${compose_file}    ${project_name}

    Exec In Packtly Service    ${compose_file}    ${project_name}    /usr/local/bin/entrypoint_gpg

Create Packtly Repo
    [Documentation]    Create an Aptly repository in the running Packtly Infra service.
    [Arguments]    ${compose_file}    ${project_name}    ${repo}

    Exec In Packtly Service    ${compose_file}    ${project_name}
    ...    create_repo    -d    ${repo}[dist]    -c    ${repo}[component]
    ...    -m    ${repo}[description]    -n    ${repo}[name]

Publish Packtly Repos
    [Documentation]    Publish one or more Aptly repositories in the running Packtly Infra service.
    [Arguments]    ${compose_file}    ${project_name}    @{repo_names}

    ${repos}=    Catenate    SEPARATOR=,    @{repo_names}
    Exec In Packtly Service    ${compose_file}    ${project_name}    publish_repo    -r    ${repos}
