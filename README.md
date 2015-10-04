# AuthLogAttackMap
Tails the /var/log/auth.log, geolocates IPs found, and displays them on a web frontend.

### Usage

You'll need two terminals: one for watching the auth.log and another for serving up events to a web frontend.

First terminal:
```
    python authLogTailer/
```
Second terminal:
```
    python sseClient.py
```
From your browser: http://localhost

Optionally you can use the CLI client:
```
    python  rpcClient.py [<command>] [<args>]

    Valid commands:
       summary    Show a summary of hosts in the auth log (Default)
       country    Show the breakdown of entries by country
       subscribe  Show json events as they occur in realtime

    optional arguments:
      -h, --help  show this help message and exit

```

### Screenshot
![ScreenShot](/screenshots/latest.png)
