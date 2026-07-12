*** Settings ***
Library    Process

*** Keywords ***
Checkout Repository
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
