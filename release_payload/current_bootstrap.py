# TG:BTC Game Assistant v7.1.1 deterministic delta updater
# Release publish trigger: 2026-08-22
import base64, gzip, hashlib, json, os, subprocess, sys
from pathlib import Path

APP_VERSION = "7.1.1"
BASE_VERSION = "7.1.0"
BASE_SHA256 = "8e26dd96da5b231432cd0f6c4090aa8c2ad832584557a5637e63d7428a6ba6c1"
NEW_SHA256 = "8abfac7af8d131963cc9b9b495f554ac58f4e096e630cf0ccaeb5bd6a45c2232"
_EDITS = """H4sIAN+OiWoC/8Va/W7bRhJ/lTnlj0gNw4iyvuxUB7i1cglwTXNOmuJgGcRaXJlEaJLHXVrSGQb6EH2CPlqf5GZ2SYqkSEl2nKuDUB/cnZ3v+c1QFxe9sdE7Ni5apx8+2J+n5x/f/fweJjBrjUzLtGatWdC6vDQujsa9vqEuFy0o/Ml4fYJLjNKX9Ce4vzBth3n+2hZuIp1wGdgyZoGIwli2O1ub+GrOIwlT9eKFQT3ZiAmRstS3epahLhuWnsFnxfcJnNHJcCqEJyQLJODxAhj44fKlzyQP5msQ85jzAISMObuBFxDxmFbzQJaOfgaSRSBc7vuwdD2fw2nMAwbXsRc4XnANnkAaYRRxx4RPLn5it6HnCLhJfOm9FHweBk6FInOu0uPnLHoVxeGcC6LCYplEEAbAb3m8ToVgc9KHWSKh1Ku1e+sJvI02ex8GvGkRimBrEfasyyxkO/zWm/PNclL5YHTUN/AyqHqBd8NN4XMetbum1e1slo9o+XG63OELSF0i5jKJA9sNb3ibjjfgJnQSn+MrW9lMSn4TSTHpd8pugP6I/87VZrj1GEiXAyngCs3yFokBKlvGoQ8scAB16C3W8Pbnn6avAU9EjXoLCDh30FSaVM5p3zLUZSOYzwRpQSK/KiCCUMLc5fMv3Cnu6+G+wVFFIYswhlQI8AJApV7ztqWEoxcvkO2inJ0Oup/VqXd5ZLlgIPI0G70jkKYnbMExlOq30Z/WMrxhvuC1i644ckpG1uEauWhrtM2Co4fPua1dVLhhXcDSH/Mxdpy1sqMBubKKwc+CuRvGttJce9YiY8xaRnpyp0niIuFm+dQ5zHFsP7xuL2YtHS932pXuT7RHpKRyN/nztz/gTrN6P2t1dhPPMhgnV7hK1CkF+ihMRncXqdQOn+JEm6E+ta0MiNYV7WmLrNbt785O3/3z3zadaJ9P33T2J92c5Ua2tmXJfPYufXP/6q7op/dKebPWLoroPXBXZvaie3lvVL+zLu/h5d9BCQh30QpXROv7BtoHiMtuuZbXXsQMs0ojj1miUbzmWcjORD7p9px7W7vnxlENKLNvQObKj+SXEnIeaO2FHzLZ3tJaB7msu2NddnackAXELivVRgrVub0e8JdZv/ZW+MUoJmoDiIFyCC2ZJ9MsVMg/VLLCRE4sc9yYhIgWlnNK/FQETw5LFQc7YsEZd67Z6ah3z1WV87jznFgOvwDHZA/PVbl7jhrdTRtFbF7QqJjwy1fm5CwXs4Xk8bbP6RxdsOvTJOpUUYSvto786vT9daFHPrZHKQRhIs4kQU5d2BQurNPVA3JSGbr1GkLtMKMq/c6Z4uoNxvv0LJWlkkKyd4eZuQJiFOwaE1wbI/a6KINY22dX3G8LtuC2FwQ8pjytWwIkIGSKqJFvflLA+5T5BEIwteSzwtOmlik9HLNA7j2ELFkiwxsUdM58JEexRneSQCL8UftogzanqYrI9eSXd/aPp+dnmNHV+59++TQ9s3sGCO+/fDLumBFDfKTT1GTWWtKuCGHLpN0zup0cUY/HXRR8bDUIvghD1LeRdm8nsCCBtJ+QfJkMrzKOizK+gPMkgFNsET6i+ohtzfUP/zDKLJc4Fp7DkV+fLyTuQI5XE+1Fit3jIfYLx8Nqv7C7GI6GY2PY6xaIDInIqIZIyXs3W4bd7tDAy+hR574mfM7jVG0vJtZr6sykuJi1QtSgz9Zi1rrE7zenjem0470M9jYMHnVxy5FVs+UAtLAyFusCqSMi1d9BqsTFUUFN2J/hZbyPcau/2dLv45Z+1aLNzDJU2wr1ZdCbNb7ZkBoQ44P+rmZyMKB6o/MMTKgNO+fzOPHQ2XQgIlHl+khY339zPsUCr6sgqny8OW50bKhLM+cRZlgW88KcArvgnIBloVNZ1qhB0fvQ3apj6DfrzoZkDz3H6h0faruCONZggFsHw0dyI3N2ZJGfIbqlNWxyy4Y+f2iNiJfRE/MyJl7GD+VleIy80GVr5lAzhiLOakcMH7HN1sXiZRhgii9UBnhVqRyQ09sMFTb08vHMNZY4KeN03DFrFac3lO0JYparH3p+unsnCm2cwenNJo0MvnbgVhgWpVOkenHyOVOjRHr/4wRSe59anv/7JK2ArwreuZ17tGYpA9V56Ae9vjTR1OgmpwBLT7rY5OjBIuFGPblEEOfN63wVz6LmCa1K78JYHbVlQTIc3j/Zh9RKmxrcpaKk3Gvgb5P6Mx48V95tEnyzjXifwb8SGr9G7loQxEPmESfR+DDEpGVmeUC1dwLICNmMKQjjG+YjPnJAhhWaedZTkA8xYZLiToGo0VdjSTXOREp+2hg7mOMCOkuUp78ZPza2e5MafdcGEJ2Kq/9DoqUKsOm7rMaVV1Ok4s36IFoa4JKj4IKmFnEJ34Pb3CWmFFwDls3dFA+uvYCbCMQS5tu4peZbokLj1GVHj1Xd+janrLG8kzs8d2zljTQQCoS3Nz2Dc/KOBXYJVwiWT4CMGrPlZvYPHGPzyvcwowht+YygQc4Q1JAkHykUoPTxhYtoyEcaIrkSHG2MdzL/lOB61y6IiNPY++BkS3xOAHnEoM5GwQ1jYDIjrsUdpnBZxC9Oepff3KwPzPcHJqSt+kWl6jFlCgU4da4+segjfaoPsmJJNFWS3jXNbyhCmt3HaWdfXfsmSIZuU3HR4aNJ6btELE6CAEsV0VGJrfNgwIMc6gz9UYUGqd6A8+mb6fn0/Y9T+9fih7cYZixGLuxFJCbWwMAQtanbS8SkOPRotF2Osch4atSoH/iJSc8cHGbMnOtUgwdN1rIZTBGY6hr052+/l0BBlgawnb1tfEpB7dKObO2uC2bf2EqNbngch/EmXBRqSJNSErBb5JKpxyON1BvNeRiOfZjHN+bzfcbZwnr752NF2xRUAe07VOh9R1lqUwmyKlFnoqpswATwvSG9n/f9fG9q1x3fGs+lgO+gfFCE/I0guNwdanr42V7pl3UtEi4M9qgbSwQh3WqVpMxmKEAMNB2E7Jl7Jl8dHFYFkKpPUcC0UJGcWQUjGQv5RcVA8XOZqHsQUbdM9G2F6Nsy0RVV3zAJnLSjVjrrwHckwqtmXtY129Zqm1vaVjlNJTtEqxPdhKOaF/YcyUgeV+Lzr2wW88KKx7TRgdb7H5S3a+SBl5m8pBir2+2a3afqPdNji/indkCizZk9DNRWMtC2+N/NJ/bp9GNoDEfdbuk3MR8UPdgK7pPy71AQ6wUYQV+wQaGfnyAWTUsZVIrSMxA0N/7Vi7lPMXR69gMulUkkjPQXMhR99EsML0jCRGQYFWPu1nOoFlXILWIu3GLzpGoW/XLiBlsjL2XD/KZzFTVOfFo4Qg/XgF1z+wYVY+cF3iS4QdVZNP2sYvvZo+KurWkVMVT6zfdgjbvd/Q6OVM15GK3bTwGnyeFGveGxoS4XlTZFjxrUz648KehNZYiW/6rKhMq0ra7pyWcaCy9GKiKE08CJQ89J/TdGH4kdpTJyXnCSyKdnUXUtzwEzhMvLy/8BwwCUzxsnAAA="""

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def find_exact_base():
    profile = Path(os.environ.get("APPDATA", Path.home())) / "TG-BTC-Arena-Companion" / "update_backups"
    candidates = []
    if profile.exists():
        candidates.extend(profile.glob("before_7.1.0_*/tg_arena_bot.py"))
        candidates.extend(profile.glob("**/tg_arena_bot.py"))
    seen=set()
    candidates=sorted(candidates,key=lambda p:p.stat().st_mtime if p.exists() else 0,reverse=True)
    for p in candidates:
        try:
            rp=str(p.resolve())
            if rp in seen: continue
            seen.add(rp)
            data=p.read_bytes()
            if sha256(data)==BASE_SHA256:
                return data
        except Exception:
            pass
    raise RuntimeError(
        "V7.1.1 needs the exact v7.1.0 updater backup, but it was not found. "
        "Run the v7.1.0 recovery/full-source update first, then run updater.py again."
    )

def main():
    target=Path(__file__).resolve()
    base=find_exact_base()
    lines=base.decode("utf-8").splitlines(keepends=True)
    edits=json.loads(gzip.decompress(base64.b64decode(_EDITS)).decode("utf-8"))
    for i1,i2,repl in sorted(edits,key=lambda x:x[0],reverse=True):
        lines[int(i1):int(i2)] = list(repl)
    out="".join(lines).encode("utf-8")
    got=sha256(out)
    if got!=NEW_SHA256:
        raise RuntimeError(f"V7.1.1 deterministic patch checksum mismatch: {got}")
    tmp=target.with_suffix(target.suffix+".v711.tmp")
    tmp.write_bytes(out)
    os.replace(tmp,target)
    flags=0x08000000 if os.name=="nt" else 0
    subprocess.Popen([sys.executable,str(target)],cwd=str(target.parent),creationflags=flags)

if __name__=="__main__":
    main()
