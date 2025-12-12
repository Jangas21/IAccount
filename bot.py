import os
import json
from datetime import date, time
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from sheets import add_gasto, add_ingreso, leer_transacciones

# ============================================================
#                   CONFIGURACIÓN INICIAL
# ============================================================

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

PROGRAMADOS_FILE = "programados.json"

def load_programados():
    if not os.path.exists(PROGRAMADOS_FILE):
        return []
    try:
        with open(PROGRAMADOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_programados(data):
    with open(PROGRAMADOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

PROGRAMADOS = load_programados()

EXPENSE_CATEGORIES = [
    "Comida", "Regalos", "Salud/médicos", "Vivienda", "Transporte",
    "Gastos personales", "Mascotas", "Suministros (luz, agua, gas, etc.)",
    "Viajes", "Deuda", "Otros"
]

INCOME_CATEGORIES = [
    "Ahorro", "Sueldo", "Bonificaciones", "Intereses", "Otros"
]

METODOS_PAGO = ["Tarjeta", "Cuenta bancaria", "Bizum", "Efectivo", "PayPal"]

USER_STATE = {}

# ============================================================
#                       HELPERS
# ============================================================

def auth_ok(update: Update) -> bool:
    usr = update.effective_user
    return usr and usr.id == ALLOWED_USER_ID

def find_programado(pid: int):
    for p in PROGRAMADOS:
        if p["id"] == pid:
            return p
    return None

def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Menú principal", callback_data="menu_main")]
    ])

def build_categories_keyboard(tipo, prefix):
    cats = EXPENSE_CATEGORIES if tipo.lower() == "gasto" else INCOME_CATEGORIES
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(c, callback_data=f"{prefix}{c}")]
        for c in cats
    ])

def build_metodos_keyboard(prefix):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(m, callback_data=f"{prefix}{m}")]
        for m in METODOS_PAGO
    ])

def build_days_keyboard(prefix):
    rows = []
    r = []
    for d in range(1, 32):
        r.append(InlineKeyboardButton(str(d), callback_data=f"{prefix}{d}"))
        if len(r) == 7:
            rows.append(r)
            r = []
    if r:
        rows.append(r)
    return InlineKeyboardMarkup(rows)

# ============================================================
#                          START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not auth_ok(update):
        await update.message.reply_text("No tienes permiso.")
        return

    msg = update.message

    keyboard = [
        [InlineKeyboardButton("📊 Ver datos", callback_data="menu_datos")],
        [InlineKeyboardButton("➖ Registrar Gasto", callback_data="menu_gasto")],
        [InlineKeyboardButton("➕ Registrar Ingreso", callback_data="menu_ingreso")],
        [InlineKeyboardButton("⚙ Programados", callback_data="menu_programados")],
    ]

    await msg.reply_text("Menú principal:", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
#                   CALLBACK PRINCIPAL
# ============================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PROGRAMADOS
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    st = USER_STATE.get(user_id, {})

    if not auth_ok(update):
        return

    # --------------------------------------------------------
    # Menú Principal
    # --------------------------------------------------------
    if data == "menu_main":
        await start(update, context)
        return

    # --------------------------------------------------------
    # VER DATOS
    # --------------------------------------------------------
    if data == "menu_datos":
        keyboard = [
            [InlineKeyboardButton("📅 Últimos movimientos", callback_data="vd_ultimos")],
            [InlineKeyboardButton("💸 Total gastos del mes", callback_data="vd_gastos_mes")],
            [InlineKeyboardButton("💰 Total ingresos del mes", callback_data="vd_ingresos_mes")],
            [InlineKeyboardButton("📈 Balance mensual", callback_data="vd_balance")],
        ]
        await query.message.reply_text("Selecciona:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --------------------------------------------------------
    # REGISTRO NORMAL GASTO / INGRESO
    # --------------------------------------------------------
    if data == "menu_gasto":
        USER_STATE[user_id] = {"tipo": "Gasto"}
        await query.message.reply_text("Introduce importe:", reply_markup=build_main_menu())
        return

    if data == "menu_ingreso":
        USER_STATE[user_id] = {"tipo": "Ingreso"}
        await query.message.reply_text("Introduce importe:", reply_markup=build_main_menu())
        return

    # --------------------------------------------------------
    # PROGRAMADOS
    # --------------------------------------------------------
    if data == "menu_programados":
        kb = [
            [InlineKeyboardButton("📄 Ver programados", callback_data="prog_ver")],
            [InlineKeyboardButton("➕ Añadir programado", callback_data="prog_add")],
            [InlineKeyboardButton("📝 Editar programado", callback_data="prog_edit")],
            [InlineKeyboardButton("❌ Eliminar programado", callback_data="prog_del")],
        ]
        await query.message.reply_text("Gestión de programados:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # --------------------------------------------------------
    # VER PROGRAMADOS
    # --------------------------------------------------------
    if data == "prog_ver":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay programados.")
            return

        txt = "Programados:\n\n"
        for p in PROGRAMADOS:
            txt += f"ID {p['id']} — {p['tipo']} — {p['importe']}€ — Día {p['dia']}\n{p['descripcion']} ({p['categoria']} · {p.get('metodo','-')})\n\n"

        await query.message.reply_text(txt, reply_markup=build_main_menu())
        return

    # --------------------------------------------------------
    # AÑADIR PROGRAMADO (PASO A PASO)
    # --------------------------------------------------------
    if data == "prog_add":
        USER_STATE[user_id] = {"modo": "add_programado", "step": "tipo"}

        kb = [
            [InlineKeyboardButton("Gasto", callback_data="addp_tipo_Gasto"),
             InlineKeyboardButton("Ingreso", callback_data="addp_tipo_Ingreso")]
        ]

        await query.message.reply_text("Selecciona tipo:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # -------- Tipo --------
    if data.startswith("addp_tipo_"):
        tipo = data.removeprefix("addp_tipo_")
        st["tipo"] = tipo
        st["step"] = "importe"
        USER_STATE[user_id] = st

        await query.message.reply_text("Introduce importe:", reply_markup=build_main_menu())
        return

    # -------- Categoría --------
    if data.startswith("addp_cat_"):
        st["categoria"] = data.removeprefix("addp_cat_")
        st["step"] = "metodo"
        USER_STATE[user_id] = st

        await query.message.reply_text("Método de pago:", reply_markup=build_metodos_keyboard("addp_met_"))
        return

    # -------- Método --------
    if data.startswith("addp_met_"):
        st["metodo"] = data.removeprefix("addp_met_")
        st["step"] = "descripcion"
        USER_STATE[user_id] = st

        await query.message.reply_text("Descripción:", reply_markup=build_main_menu())
        return

    # -------- Día --------
    if data.startswith("addp_dia_"):
        st["dia"] = int(data.removeprefix("addp_dia_"))
        st["step"] = "confirmar"
        USER_STATE[user_id] = st

        texto = (
            f"Confirmar programado:\n\n"
            f"Tipo: {st['tipo']}\n"
            f"Importe: {st['importe']}€\n"
            f"Categoría: {st['categoria']}\n"
            f"Método: {st['metodo']}\n"
            f"Día: {st['dia']}\n"
            f"Descripción: {st['descripcion']}\n"
        )

        kb = [
            [InlineKeyboardButton("✅ Confirmar", callback_data="addp_conf_si")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="addp_conf_no")],
        ]

        await query.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(kb))
        return

    # -------- Confirmación --------
    if data == "addp_conf_si":
        new_id = max([p["id"] for p in PROGRAMADOS], default=0) + 1

        PROGRAMADOS.append({
            "id": new_id,
            "tipo": st["tipo"],
            "dia": st["dia"],
            "importe": st["importe"],
            "descripcion": st["descripcion"],
            "categoria": st["categoria"],
            "metodo": st["metodo"],
        })

        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}

        await query.message.reply_text(f"Añadido (ID {new_id})", reply_markup=build_main_menu())
        return

    if data == "addp_conf_no":
        USER_STATE[user_id] = {}
        await query.message.reply_text("Cancelado.", reply_markup=build_main_menu())
        return

    # --------------------------------------------------------
    # ELIMINAR PROGRAMADO
    # --------------------------------------------------------
    if data == "prog_del":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay programados.")
            return

        kb = [
            [InlineKeyboardButton(f"Eliminar ID {p['id']}", callback_data=f"del_{p['id']}")]
            for p in PROGRAMADOS
        ]

        await query.message.reply_text(
            "Selecciona:", reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("del_"):
        pid = int(data.removeprefix("del_"))
        PROGRAMADOS = [p for p in PROGRAMADOS if p["id"] != pid]
        save_programados(PROGRAMADOS)

        await query.message.reply_text("Eliminado.", reply_markup=build_main_menu())
        return

    # --------------------------------------------------------
    # EDITAR PROGRAMADO
    # --------------------------------------------------------
    if data == "prog_edit":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay programados.")
            return

        kb = [
            [InlineKeyboardButton(f"Editar ID {p['id']}", callback_data=f"edit_{p['id']}")]
            for p in PROGRAMADOS
        ]

        USER_STATE[user_id] = {"modo": "edit_programado", "step": "select"}
        await query.message.reply_text("Selecciona:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("edit_"):
        pid = int(data.removeprefix("edit_"))
        if not find_programado(pid):
            await query.message.reply_text("Programado no encontrado.")
            return

        USER_STATE[user_id] = {"modo": "edit_programado", "edit_id": pid}

        kb = [
            [InlineKeyboardButton("Tipo", callback_data="field_tipo")],
            [InlineKeyboardButton("Importe", callback_data="field_importe")],
            [InlineKeyboardButton("Categoría", callback_data="field_categoria")],
            [InlineKeyboardButton("Método", callback_data="field_metodo")],
            [InlineKeyboardButton("Descripción", callback_data="field_desc")],
            [InlineKeyboardButton("Día", callback_data="field_dia")],
        ]

        await query.message.reply_text("¿Qué quieres cambiar?", reply_markup=InlineKeyboardMarkup(kb))
        return

    # -------- EDITAR CAMPOS INDIVIDUALES --------

    if data.startswith("field_"):
        field = data.removeprefix("field_")
        st["step"] = field
        USER_STATE[user_id] = st

        prog = find_programado(st["edit_id"])

        if field == "tipo":
            kb = [
                [InlineKeyboardButton("Gasto", callback_data="set_tipo_Gasto"),
                 InlineKeyboardButton("Ingreso", callback_data="set_tipo_Ingreso")]
            ]
            await query.message.reply_text("Nuevo tipo:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if field == "categoria":
            await query.message.reply_text("Nueva categoría:",
                reply_markup=build_categories_keyboard(prog["tipo"], "set_cat_"))
            return

        if field == "metodo":
            await query.message.reply_text("Nuevo método:",
                reply_markup=build_metodos_keyboard("set_met_"))
            return

        if field == "dia":
            await query.message.reply_text("Nuevo día:", reply_markup=build_days_keyboard("set_dia_"))
            return

        # importe o descripción → se responden por texto
        if field in ["importe", "desc"]:
            await query.message.reply_text("Introduce el nuevo valor:")
            return

    # SETTERS DIRECTOS
    if data.startswith("set_tipo_"):
        p = find_programado(st["edit_id"])
        p["tipo"] = data.removeprefix("set_tipo_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Tipo actualizado.", reply_markup=build_main_menu())
        return

    if data.startswith("set_cat_"):
        p = find_programado(st["edit_id"])
        p["categoria"] = data.removeprefix("set_cat_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Categoría actualizada.", reply_markup=build_main_menu())
        return

    if data.startswith("set_met_"):
        p = find_programado(st["edit_id"])
        p["metodo"] = data.removeprefix("set_met_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Método actualizado.", reply_markup=build_main_menu())
        return

    if data.startswith("set_dia_"):
        p = find_programado(st["edit_id"])
        p["dia"] = int(data.removeprefix("set_dia_"))
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Día actualizado.", reply_markup=build_main_menu())
        return

    # --------------------------------------------------------
    # REGISTRO NORMAL: Categoría / Método / Confirmación
    # --------------------------------------------------------

    if data.startswith("cat_"):
        st["categoria"] = data.removeprefix("cat_")
        USER_STATE[user_id] = st

        await query.message.reply_text(
            "Método:",
            reply_markup=build_metodos_keyboard("met_")
        )
        return

    if data.startswith("met_"):
        st["metodo"] = data.removeprefix("met_")
        USER_STATE[user_id] = st

        st["descripcion"] = f"{st['categoria']} · {st['metodo']}"

        texto = (
            f"Confirmar:\n\n"
            f"Tipo: {st['tipo']}\n"
            f"Importe: {st['importe']}€\n"
            f"Categoría: {st['categoria']}\n"
            f"Método: {st['metodo']}\n"
            f"Descripción: {st['descripcion']}\n"
        )

        kb = [
            [InlineKeyboardButton("✅ Confirmar", callback_data="conf_si")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="conf_no")],
        ]

        await query.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(kb))
        return

    if data == "conf_si":
        hoy = date.today()
        if st["tipo"] == "Gasto":
            add_gasto(hoy, st["importe"], st["descripcion"], st["categoria"])
        else:
            add_ingreso(hoy, st["importe"], st["descripcion"], st["categoria"])

        USER_STATE[user_id] = {}

        await query.message.reply_text("Guardado!", reply_markup=build_main_menu())
        return

    if data == "conf_no":
        USER_STATE[user_id] = {}
        await query.message.reply_text("Cancelado.", reply_markup=build_main_menu())
        return

# ============================================================
#                     TEXT HANDLER
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not auth_ok(update):
        return

    st = USER_STATE.get(user_id, {})
    if not st:
        await update.message.reply_text("Usa /start para comenzar.")
        return

    # ---- AÑADIR PROGRAMADO ----
    if st.get("modo") == "add_programado":
        step = st["step"]

        if step == "importe":
            try:
                st["importe"] = float(text.replace(",", "."))
            except:
                await update.message.reply_text("Importe inválido.")
                return

            st["step"] = "categoria"
            USER_STATE[user_id] = st
            await update.message.reply_text("Categoría:",
                reply_markup=build_categories_keyboard(st["tipo"], "addp_cat_"))
            return

        if step == "descripcion":
            st["descripcion"] = text
            st["step"] = "dia"
            USER_STATE[user_id] = st
            await update.message.reply_text("Día:", reply_markup=build_days_keyboard("addp_dia_"))
            return

    # ---- EDITAR PROGRAMADO ----
    if st.get("modo") == "edit_programado":
        p = find_programado(st["edit_id"])

        if st["step"] == "importe":
            try:
                p["importe"] = float(text.replace(",", "."))
            except:
                await update.message.reply_text("Importe inválido.")
                return
            save_programados(PROGRAMADOS)
            USER_STATE[user_id] = {}
            await update.message.reply_text("Importe actualizado.", reply_markup=build_main_menu())
            return

        if st["step"] == "desc":
            p["descripcion"] = text
            save_programados(PROGRAMADOS)
            USER_STATE[user_id] = {}
            await update.message.reply_text("Descripción actualizada.", reply_markup=build_main_menu())
            return

    # ---- REGISTRO NORMAL ----
    if "importe" not in st:
        try:
            st["importe"] = float(text.replace(",", "."))
        except:
            await update.message.reply_text("Importe inválido.")
            return

        categorias = EXPENSE_CATEGORIES if st["tipo"] == "Gasto" else INCOME_CATEGORIES

        kb = [
            [InlineKeyboardButton(c, callback_data=f"cat_{c}")]
            for c in categorias
        ]

        USER_STATE[user_id] = st

        await update.message.reply_text("Categoría:", reply_markup=InlineKeyboardMarkup(kb))
        return

# ============================================================
#               EJECUCIÓN DIARIA DE PROGRAMADOS
# ============================================================

async def ejecutar_programados(context):
    hoy = date.today()

    for p in PROGRAMADOS:
        if p["dia"] == hoy.day:
            desc = f"{p['descripcion']} · {p['metodo']}"
            if p["tipo"].lower() == "gasto":
                add_gasto(hoy, p["importe"], desc, p["categoria"])
            else:
                add_ingreso(hoy, p["importe"], desc, p["categoria"])

# ============================================================
#                           MAIN
# ============================================================

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Programados (DESPUÉS de build, ANTES de polling)
    application.job_queue.run_daily(ejecutar_programados, time(7, 0))

    print("Bot iniciado con polling (PTB 21 + Python 3.13)")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()

