*** Settings ***
Library    Process
Library    String
Library    OperatingSystem

*** Variables ***
${GEN_GPG_SCRIPT}    ${EMPTY}

*** Keywords ***
Get Gen GPG Script
    ${result}=    Run Process    git    rev-parse    --show-toplevel
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}
    ${topdir}=    Strip String    ${result.stdout}
    RETURN    ${topdir}/packtly-builder/containers/scripts/gen_gpg

Generate GPG Keys
    [Arguments]
    ...    ${keys_dir}
    ...    ${image}
    ...    ${name}=packtly-test
    ...    ${email}=test@packtly.local
    ...    ${pass}=test1234

    ${gpg_out}=    Set Variable    ${keys_dir}/_gpg_out
    ${gen_gpg}=    Get Gen GPG Script

    Create Directory    ${keys_dir}/public
    Create Directory    ${keys_dir}/private
    Create Directory    ${gpg_out}

    ${result}=    Run Process
    ...    podman    run    --rm
    ...    --entrypoint    /usr/local/bin/gen_gpg
    ...    -v    ${gen_gpg}:/usr/local/bin/gen_gpg:Z,ro
    ...    -v    ${gpg_out}:/opt/keys/gpg:Z
    ...    ${image}
    ...    --name    ${name}
    ...    --email    ${email}
    ...    --pass    ${pass}
    ...    stdout=PIPE    stderr=PIPE

    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

    Move File    ${gpg_out}/repo_signing.key             ${keys_dir}/public/repo_signing.key
    Move File    ${gpg_out}/repo_signing_private.key     ${keys_dir}/private/repo_signing_private.key
    Move File    ${gpg_out}/repo_signing_private_pass    ${keys_dir}/private/repo_signing_private_pass

    Remove Directory    ${gpg_out}    recursive=True
