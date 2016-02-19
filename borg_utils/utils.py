import hashlib

def file_md5(f):
    md5 = hashlib.md5()
    with open(f,"rb") as f:
        for chunk in iter(lambda: f.read(2048),b""):
            md5.update(chunk)
    return md5.hexdigest()

