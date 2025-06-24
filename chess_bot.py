import nest_asyncio
nest_asyncio.apply()

import chess
import chess.engine
import chess.svg
import cairosvg
import io
from telegram import Update, InputFile, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

import platform

if platform.system() == "Darwin":
    ENGINE_PATH = "engine/stockfish-macos"
else:
    ENGINE_PATH = "engine/stockfish-linux"
engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)


command_buttons = ReplyKeyboardMarkup([
    ["/newgame", "/board"],
    ["/board_on", "/board_off"]
], resize_keyboard=True)

engine = None  # глобальный движок

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.bot_data['board'] = chess.Board()
    context.application.bot_data['auto_board'] = False
    await update.message.reply_text(
        "👋 Добро пожаловать в DarkChessBot!\n\n"
        "♟ Ходы вводятся в формате длинного SAN.\n"
        "Пример: Nb1c3 (Конь с b1 на c3)\n\n"
        "Перевод фигур:\n"
        "K: (King) - король\n"
        "Q: (Queen) - ферзь\n"
        "R: (Rook) - ладья\n"
        "B: (Bishop) - слон\n"
        "N: (Knight) - конь (буква \"N\" используется, чтобы избежать путаницы с \"K\" - королём)\n"
        "Пешки - не обозначаются, просто указывается клетка, куда они ходят\n\n"
        "📷 /board — показать доску\n"
        "🖼 /board_on — включить авто-доску\n"
        "🛑 /board_off — выключить авто-доску\n"
        "♟ /newgame — начать новую партию",
        reply_markup=command_buttons
    )

async def board_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.bot_data['auto_board'] = True
    await update.message.reply_text("🟢 Автоматический показ доски включён.", reply_markup=command_buttons)

async def board_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.bot_data['auto_board'] = False
    await update.message.reply_text("🔴 Автоматический показ доски выключен.", reply_markup=command_buttons)

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.application.bot_data['board'] = chess.Board()
    await update.message.reply_text("♟ Новая партия началась! Ваш ход.", reply_markup=command_buttons)

async def send_board(update: Update, context: ContextTypes.DEFAULT_TYPE):
    board = context.application.bot_data.get('board')
    if board is None:
        board = chess.Board()
        context.application.bot_data['board'] = board

    svg_code = chess.svg.board(
        board=board,
        colors={
            "square light": "#5a5a6d",
            "square dark": "#2e2e3e",
            "last move": "#4c6fd1",
            "coordinates": "#e0e4f0"
        }
    )
    png_data = cairosvg.svg2png(bytestring=svg_code.encode("utf-8"))
    bio = io.BytesIO(png_data)
    bio.name = 'board.png'
    bio.seek(0)
    await update.message.reply_photo(photo=InputFile(bio), caption="Текущая позиция доски", reply_markup=command_buttons)

def format_long_san(move, board):
    piece = board.piece_at(move.from_square)
    if not piece:
        return move.uci()
    piece_letter = {
        chess.KNIGHT: "N",
        chess.BISHOP: "B",
        chess.ROOK: "R",
        chess.QUEEN: "Q",
        chess.KING: "K"
    }.get(piece.piece_type, "")

    pieces_same_type = list(board.pieces(piece.piece_type, piece.color))
    if len(pieces_same_type) > 1:
        return f"{piece_letter}{chess.square_name(move.from_square)}{chess.square_name(move.to_square)}"
    return f"{piece_letter}{chess.square_name(move.from_square)}{chess.square_name(move.to_square)}"

def parse_long_san(move_text, board):
    move_text = move_text.strip().replace("-", "").replace(" ", "")
    piece_map = {'K': chess.KING, 'Q': chess.QUEEN, 'R': chess.ROOK,
                 'B': chess.BISHOP, 'N': chess.KNIGHT}

    if len(move_text) == 4:
        from_sq = move_text[0:2]
        to_sq = move_text[2:4]
        from_square = chess.parse_square(from_sq)
        to_square = chess.parse_square(to_sq)

        for move in board.legal_moves:
            if move.from_square == from_square and move.to_square == to_square:
                return move
        raise ValueError("Неверный пешечный ход")

    elif len(move_text) == 5 or len(move_text) == 6:
        piece_letter = move_text[0].upper()
        from_sq = move_text[1:3]
        to_sq = move_text[3:5]
        from_square = chess.parse_square(from_sq)
        to_square = chess.parse_square(to_sq)

        wanted_piece_type = piece_map.get(piece_letter)
        if not wanted_piece_type:
            raise ValueError("Неверная фигура")

        for move in board.legal_moves:
            if move.from_square == from_square and move.to_square == to_square:
                piece = board.piece_at(from_square)
                if piece and piece.piece_type == wanted_piece_type:
                    return move
        raise ValueError("Неверный ход для фигуры")
    else:
        raise ValueError("Неверный формат хода")

async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global engine

    board = context.application.bot_data.get('board')
    if board is None:
        board = chess.Board()
        context.application.bot_data['board'] = board

    auto_board = context.application.bot_data.get('auto_board', False)

    move_text = update.message.text

    try:
        move = parse_long_san(move_text, board)
    except ValueError as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}\nПример хода: Nb1c3 или e2e4.", reply_markup=command_buttons)
        return

    if move not in board.legal_moves:
        await update.message.reply_text(f"❗ Ход {move_text} не разрешён.", reply_markup=command_buttons)
        return

    board.push(move)

    result = engine.play(board, chess.engine.Limit(time=0.1))
    board.push(result.move)

    san_move = format_long_san(result.move, board)
    await update.message.reply_text(f"🤖 Ход бота: {san_move}", reply_markup=command_buttons)

    context.application.bot_data['board'] = board

    if auto_board:
        await send_board(update, context)

async def main():
    global engine
    engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)

    app = Application.builder().token("8135783123:AAHPsQ8Z0jMYYYvv94egENFLEwJoGpnd0_0").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", new_game))
    app.add_handler(CommandHandler("board", send_board))
    app.add_handler(CommandHandler("board_on", board_on))
    app.add_handler(CommandHandler("board_off", board_off))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_move))

    await app.run_polling()
    engine.quit()

if __name__ == "__main__":
    asyncio.run(main())

