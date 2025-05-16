# DNA Center Dynamic Inventory

Using these files requires creating a custom credential type in AAP so that the host, username, and password for DNA Center are passed as environment variables.

    
Input configuration:
```
fields:
  - id: host
    type: string
    label: Host
  - id: username
    type: string
    label: Username
  - id: password
    type: string
    label: Password
    secret: true
required:
  - host
  - username
  - password
```
Injector configuration:
```
env:
  DNAC_HOST: '{{ host }}'
  DNAC_PASSWORD: '{{ password }}'
  DNAC_USERNAME: '{{ username }}'
```
