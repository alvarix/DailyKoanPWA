There was a catastrophic failure with the deploy plan. 
It took down my client site on the server, despite specific planning to protect client site as mission critical.
Forge: Sites > DailyKoan > ... > Edit NGNINX Settings
overwrote the contents with the LLM specified settings for DailyKoan Python app to work. 
I explicitly asked and was told that editing these settings would be sandboxed to that site. 
The debugging chatgpt told me that probable when the NGINX config file was next hit - a reboot or something, it had bad syntax and crashed the nginx server for the whole droplet.
I backed up and deleted the site.config and rebooted the server.   


```
forge@alfaForge:~$ mkdir -p ~/nginx-backup
sudo cp /etc/nginx/forge-conf/3430825/site.conf ~/nginx-backup/site.conf.bak
sudo cp /etc/nginx/sites-available/dailykoan.on-forge.com ~/nginx-backup/dailykoan.on-forge.com.bak
sudo truncate -s 0 /etc/nginx/forge-conf/3430825/site.conf
sudo nginx -t
```
Syntax OK > restart
```
sudo systemctl restart nginx


# 10/27/26
Client reported site down.
Restart nginx which crashed the 24th.
as a result of changing NGINX settings on Forge 
- purpose: deploy DailyKoan on same droplet
  Agent assured me NGINX changing were sandboxed
- Debugging [chatgpt](https://chatgpt.com/share/6ae21047-7444-83e9-ba38-5a8d7a546a7b):
```
forge@alfaForge:~$ sudo nginx -t

2026/10/27 23:20:02 [emerg] 2568801#2568801: "server" directive is not allowed here in /etc/nginx/forge-conf/3430825/site.conf:1
...
     Loaded: loaded (/usr/lib/systemd/system/nginx.service; enabled; preset: enabled)
     Active: failed (Result: exit-code) since Sat 2026-10-24 06:57:36 UTC; 3 days ago
   Duration: 1w 2d 5min 30.447s
    Docs: man:nginx(8)
    Process: 2499816 ExecStartPre=/usr/sbin/nginx -t -q -g daemon on; master_process on; (code=exited, status=1/FAILURE)
        CPU: 11ms
```

```
forge@alfaForge:~$ sudo systemctl status nginx --no-pager

Oct 24 06:57:36 alfaForge systemd[1]: Starting nginx.service - A high perfo…r...
Oct 24 06:57:36 alfaForge nginx[2499816]: 2026/10/24 06:57:36 [emerg] 24998…nf:1
Oct 24 06:57:36 alfaForge nginx[2499816]: nginx: configuration file /etc/ng…iled
Oct 24 06:57:36 alfaForge systemd[1]: nginx.service: Control process exited…LURE
Oct 24 06:57:36 alfaForge systemd[1]: nginx.service: Failed with result 'ex…de'.
Oct 24 06:57:36 alfaForge systemd[1]: Failed to start nginx.service - A hig…ver.
Hint: Some lines were ellipsized, use -l to show in full.