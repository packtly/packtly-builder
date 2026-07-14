*** Settings ***
Documentation    Keywords for generating GPG key pairs used to sign and verify Debian packages in integration tests.
Library    OperatingSystem
Library    Process
Library    String


*** Variables ***
${GEN_GPG_SCRIPT}    ${EMPTY}
${GPG_NAME}          packtly-test
${GPG_EMAIL}         test@packtly.local
${GPG_PASS}          test1234


*** Keywords ***
Get Gen GPG Script
    [Documentation]    Return the absolute path to the gen_gpg helper script in the repository.
    ${result}=    Run Process    git    rev-parse    --show-toplevel
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}
    ${topdir}=    Strip String    ${result.stdout}
    RETURN    ${topdir}/packtly-builder/containers/scripts/gen_gpg

Generate GPG Keys
    [Documentation]    Generate a GPG key pair inside the build container and export its files.
    ...    The public and private keys are written to ${keys_dir}.
    [Arguments]    ${keys_dir}
    ...    ${image}

    VAR    ${gpg_out}    ${keys_dir}/_gpg_out
    ${gen_gpg}=    Get Gen GPG Script

    Prepare GPG Key Directories    ${keys_dir}    ${gpg_out}
    Run GPG Generator    ${gen_gpg}    ${gpg_out}    ${image}
    Export GPG Keys    ${gpg_out}    ${keys_dir}
    Remove Directory    ${gpg_out}    recursive=True

Prepare GPG Key Directories
    [Documentation]    Create the public, private, and temporary GPG key directories.
    [Arguments]    ${keys_dir}    ${gpg_out}

    Create Directory    ${keys_dir}/public
    Create Directory    ${keys_dir}/private
    Create Directory    ${gpg_out}

Run GPG Generator
    [Documentation]    Run the GPG generation helper in the specified build container.
    [Arguments]    ${gen_gpg}    ${gpg_out}    ${image}

    ${result}=    Run Process
    ...    podman    run    --rm
    ...    --entrypoint    /usr/local/bin/gen_gpg
    ...    -v    ${gen_gpg}:/usr/local/bin/gen_gpg:Z,ro
    ...    -v    ${gpg_out}:/opt/keys/gpg:Z
    ...    ${image}
    ...    --name    ${GPG_NAME}
    ...    --email    ${GPG_EMAIL}
    ...    --pass    ${GPG_PASS}

    Log    ${result.stdout}
    Log    ${result.stderr}
    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}

Export GPG Keys
    [Documentation]    Move generated GPG key material from the temporary directory to ${keys_dir}.
    [Arguments]    ${gpg_out}    ${keys_dir}

    Move File    ${gpg_out}/repo_signing.key             ${keys_dir}/public/repo_signing.key
    Move File    ${gpg_out}/repo_signing_private.key     ${keys_dir}/private/repo_signing_private.key
    Move File    ${gpg_out}/repo_signing_private_pass    ${keys_dir}/private/repo_signing_private_pass
