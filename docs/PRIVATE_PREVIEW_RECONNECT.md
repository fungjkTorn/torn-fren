# Reconnect the private preview after a PC restart

The private beta runs on the VM at loopback port 8765. Windows reaches it through SSH port forwarding. Restarting Windows closes that connection; restoring the tunnel does not require changing or restarting the VM service.

Open PowerShell and run:

```powershell
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -i "$env:USERPROFILE\Desktop\.ssh\torn-fren.key" -L 127.0.0.1:8765:127.0.0.1:8765 ubuntu@150.136.108.146
```

Leave that window open, then visit http://127.0.0.1:8765/. A connected SSH command with no output is normal. Ctrl+C closes the tunnel. Never paste private key contents into chat. This command uses the existing local key file; it does not change SSH trust settings or expose the VM port publicly.

If SSH reports that port 8765 is already in use, do not kill an unknown process. Try the page first; an existing tunnel may already be connected. If SSH connects but the page fails, the VM service needs a separate status check. A page loading does not establish fresh data or model accuracy.

Windows sign-in could launch this same command using a local shortcut, but it still depends on the PC being on, network connectivity and the existing key. No Windows startup task has been installed remotely. The production website and original V2/experimental pages are separate from this private preview.
