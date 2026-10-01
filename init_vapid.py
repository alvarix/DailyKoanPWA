# pyright: reportMissingImports=false
#!/usr/bin/env python3
"""Generate VAPID keys for Web Push."""

from py_vapid import Vapid


def generate_keys():
    try:
        vapid = Vapid()
        vapid.generate_keys()
        private_key = vapid.private_pem()
        public_key = vapid.public_pem()

        with open('vapid_private.pem', 'wb') as f:
            f.write(private_key)

        with open('vapid_public.pem', 'wb') as f:
            f.write(public_key)

        print("VAPID keys generated:")
        print("  vapid_private.pem")
        print("  vapid_public.pem")
        # Also print the base64 public key for JS
        from cryptography.hazmat.primitives import serialization
        from py_vapid import b64urlencode
        pub_key = vapid._public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        print(f"\nPublic key (for frontend): {b64urlencode(pub_key)}")
    except Exception as e:
        print(f"Error generating VAPID keys: {e}")
        raise


if __name__ == '__main__':
    generate_keys()
