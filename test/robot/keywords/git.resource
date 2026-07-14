*** Settings ***
Documentation    Keywords for interacting with Git repositories in integration tests.
Library    Process


*** Keywords ***
Checkout Repository
    [Documentation]    Checkout a git repository to a given path.
    [Arguments]    ${url}    ${path}    ${branch}=main

    ${result}=    Run Process
    ...    git
    ...    clone
    ...    --depth
    ...    1
    ...    --branch
    ...    ${branch}
    ...    ${url}
    ...    ${path}

    Should Be Equal As Integers    ${result.rc}    0    ${result.stderr}
