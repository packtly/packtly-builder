*** Settings ***
Documentation    Keywords for generating Aptly credentials used in integration tests.
Library    OperatingSystem


*** Keywords ***
Generate Aptly Credentials
    [Documentation]    Generate a simple aptly credentials file
    [Arguments]    ${path}
    ...    ${username}=admin
    ...    ${password}=password

    Create File    ${path}    username=${username}\npassword=${password}
