"""Generate a random encryption key for the credential vault."""
import secrets

if __name__ == "__main__":
    key = secrets.token_urlsafe(32)
    print(f"ENCRYPTION_KEY={key}")
    print("\nAdd this to your .env file.")
