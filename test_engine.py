import chess
import chess.engine

engine = chess.engine.SimpleEngine.popen_uci("/Users/viktoria/Desktop/darkchess_bot/engine/stockfish 2/stockfish-macos-x86-64-bmi2")

print("Engine запущен!")
engine.quit()
