# Third-party software used by the gateway

## segno 1.6.6

- Use: draws the TOTP enrolment `otpauth://` URI as a QR code (SVG data URI) on this machine, in
  `src/gateway/app.py` (`qr_svg_data_uri`). Nothing is sent to a CDN or a QR web service.
- Source: https://github.com/heuer/segno/ (PyPI package `segno`, pinned `segno==1.6.6` in `requirements.txt`).
- Pure Python, no dependencies. Licence: BSD-3-Clause, text below (copied from the 1.6.6 wheel's
  `segno-1.6.6.dist-info/licenses/LICENSE`).

```
Copyright (c) 2016 - 2025, Lars Heuer
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## cryptography

- Use: AES-256-GCM and HKDF-SHA256 for the encrypted backup archives (`src/gateway/backup_crypto.py`).
- Source: https://github.com/pyca/cryptography (PyPI `cryptography`, `>=42,<46` in `requirements.txt`).
- Licence: Apache-2.0 OR BSD-3-Clause (dual); wheels bundle OpenSSL (Apache-2.0).
