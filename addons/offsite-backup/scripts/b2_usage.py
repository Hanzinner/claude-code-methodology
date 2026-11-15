#!/usr/bin/env python3
"""Print how many bytes REALLY lie in the Backblaze B2 bucket (every file version) - the number the free-tier cap counts.

Why not `restic stats`: it counts live data only (8.53 GB one day) while the bucket held 9.98 GB - unused pack parts and
service files. The alarm stayed silent until the storage hit the cap and backups failed for two days.
One b2_list_file_versions call (class C, 2500 free per day) per 10 000 files. Prints the byte count.
Key and bucket come from restic-env.sh: B2_ACCOUNT_ID, B2_ACCOUNT_KEY (+ B2_BUCKET when the key is not bucket-restricted).
B2_AUTH_URL overrides the authorize endpoint (tests only)."""
import base64, json, os, sys, urllib.request

AUTH = os.environ.get("B2_AUTH_URL") or "https://api.backblazeb2.com/b2api/v3/b2_authorize_account"


def call(url, token=None, body=None, timeout=60):
    headers = {"Authorization": token} if token else {}
    data = json.dumps(body).encode() if body is not None else None
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout))


def main():
    k, s = os.environ["B2_ACCOUNT_ID"], os.environ["B2_ACCOUNT_KEY"]
    a = call(AUTH, "Basic " + base64.b64encode(f"{k}:{s}".encode()).decode(), timeout=30)
    api = a["apiInfo"]["storageApi"]
    token = a["authorizationToken"]
    bucket_id = api.get("bucketId")
    if not bucket_id:                              # an unrestricted key: look the bucket up by name
        name = os.environ.get("B2_BUCKET")
        if not name:
            sys.exit("b2_usage: key is not bucket-restricted and B2_BUCKET is not set")
        r = call(api["apiUrl"] + "/b2api/v3/b2_list_buckets", token, {"accountId": api.get("accountId") or a.get("accountId"), "bucketName": name})
        bucket_id = r["buckets"][0]["bucketId"]
    total, n, nid = 0, None, None
    while True:
        body = {"bucketId": bucket_id, "maxFileCount": 10000}
        if n:
            body.update(startFileName=n, startFileId=nid)
        r = call(api["apiUrl"] + "/b2api/v3/b2_list_file_versions", token, body)
        total += sum(f.get("contentLength", 0) for f in r["files"])
        n, nid = r.get("nextFileName"), r.get("nextFileId")
        if not n:
            print(total)
            return


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.exit(f"b2_usage: {e}")
