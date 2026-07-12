# acs-auto-sit-tools

Local Python tool for ACS automated SIT of 3DS browser-based AReq and CReq/CRes flows.

## Run

```powershell
python -m acs_auto_sit --host 127.0.0.1 --port 8000
```

For intranet access:

```powershell
python -m acs_auto_sit --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/`.

## MVP Flow

1. Paste the ACS AReq URL, headers, and AReq JSON.
2. Submit AReq. The backend sends an HTTPS POST and displays the ARes.
3. If ARes has `transStatus = "C"`, the tool generates the first editable CReq draft.
4. Submit CReq. The backend sends a POST and displays the CRes.
5. If CRes still has `transStatus = "C"`, edit the next CReq draft, for example with OTP in `challengeDataEntry`, and submit again.

There is no login in this version. All ACS transaction requests are POST.
