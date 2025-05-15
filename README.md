# DNA Center Dynamic Inventory

Using these files requires creating a custom credential type in AAP so that the host, username, and password for DNA Center are passed as environment variables.

    
Input configuration:
```
fields:
  - id: username
    type: string
    label: Username
  - id: password
    type: string
    label: Password
    secret: true
  - id: host
    type: string
    label: Host
required:
  - username
  - password
  - host
```
Injector configuration:
```
env:
  DNAC_HOST: '{{ host }}'
  DNAC_PASSWORD: '{{ password }}'
  DNAC_USERNAME: '{{ username }}'
```
