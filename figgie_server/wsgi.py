import os
from figgie_server import db
from figgie_server.api import app   # your Flask() instance
from figgie_server.game import Game

db.init_db()
app.game = Game()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)