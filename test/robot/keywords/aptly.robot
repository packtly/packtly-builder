*** Settings ***
Library    OperatingSystem

*** Keywords ***
Generate Aptly Credentials
    [Arguments]
    ...    ${path}
    ...    ${username}=admin
    ...    ${password}=password

    Create File    ${path}    username=${username}\npassword=${password}
