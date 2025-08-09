Olimpiad Abyss — working build

Run locally:
1. python -m venv venv
2. On Windows Powershell: .\venv\Scripts\Activate.ps1  (or use activate)
   On Unix: source venv/bin/activate
3. pip install -r requirements.txt
4. Create a .env file in project root (optional):
   SECRET_KEY=your_secret_here
   GOD_USERNAME=your_god_login
   GOD_PASSWORD=your_god_password
5. python app.py
6. Open http://127.0.0.1:5000