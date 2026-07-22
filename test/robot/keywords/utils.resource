*** Settings ***
Documentation    Common utility keywords for Robot Framework integration tests.
Library    OperatingSystem
Library    Process
Library    String


*** Keywords ***
Run Process And Log
    [Documentation]    Run a process and log the return code, stdout, and stderr.
    [Arguments]    @{command}

    ${result}=    Run Process    @{command}

    Log    RC: ${result.rc}
    Log    STDOUT:\n${result.stdout}
    Log    STDERR:\n${result.stderr}

    Should Be Equal As Integers    ${result.rc}    0

    RETURN    ${result}

Execute In Test Container
    [Documentation]    Execute a shell command inside a container.
    [Arguments]    ${container}    ${command}

    Run Process And Log
    ...    podman
    ...    exec
    ...    ${container}
    ...    sh
    ...    -c
    ...    ${command}
