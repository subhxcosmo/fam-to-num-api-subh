#!/bin/bash
echo "Setting up Telegram FAM API..."

# Install dependencies
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# Telegram API credentials - get from https://my.telegram.org/apps
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here

# Session string (generate with python generate_session.py)
TELEGRAM_SESSION_STRING=your_session_string_here

# Optional: Phone number for first-time setup
# TELEGRAM_PHONE=+919876543210

# Optional: 2FA password if enabled
# TELEGRAM_PASSWORD=your_2fa_password
EOF
    echo "✅ Created .env file. Please edit it with your credentials."
fi

echo "Setup complete!"
echo "Next steps:"
echo "1. Edit .env with your Telegram credentials"
echo "2. Generate session string: python generate_session.py"
echo "3. Test session: python test_session.py"
echo "4. Run the API: python app.py"
