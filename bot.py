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
from flask import Flask, request

app_flask = Flask(__name__)
load_dotenv()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

PROGRAMADOS_FILE = "programados.json"


# ============================================================
#                      PERSISTENCIA JSON
# ============================================================

def load_programados():
    if not os.path.exists(PROGRAMADOS_FILE):
        return []
    try:
        with open(PROGRAMADOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_programados(data):
    with open(PROGRAMADOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


PROGRAMADOS = load_programados()


# ============================================================
#                      CONFIGURACIÓN
# ============================================================

EXPENSE_CATEGORIES = [
    "Comida",
    "Regalos",
    "Salud/médicos",
    "Vivienda",
    "Transporte",
    "Gastos personales",
    "Mascotas",
    "Suministros (luz, agua, gas, etc.)",
    "Viajes",
    "Deuda",
    "Otros",
]

INCOME_CATEGORIES = [
    "Ahorro",
    "Sueldo",
    "Bonificaciones",
    "Intereses",
    "Otros",
]

METODOS_PAGO = ["Tarjeta", "Cuenta bancaria", "Bizum", "Efectivo", "PayPal"]

USER_STATE = {}


# ============================================================
#                 BOTÓN “MENÚ PRINCIPAL”
# ============================================================

def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Menú principal", callback_data="menu_main")]
    ])


# ============================================================
#                     BOTÓN PERSISTENTE
# ============================================================

async def setup_bot_menu(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Abrir menú principal")
    ])


# ============================================================
#                          HELPERS
# ============================================================

def auth_ok(update: Update) -> bool:
    usr = update.effective_user
    return usr and usr.id == ALLOWED_USER_ID


def find_programado(pid: int):
    for p in PROGRAMADOS:
        if p["id"] == pid:
            return p
    return None


def build_days_keyboard(prefix: str):
    rows = []
    row = []
    for d in range(1, 32):
        row.append(InlineKeyboardButton(str(d), callback_data=f"{prefix}{d}"))
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def build_categories_keyboard(tipo: str, prefix: str):
    cats = EXPENSE_CATEGORIES if tipo.lower() == "gasto" else INCOME_CATEGORIES
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(c, callback_data=f"{prefix}{c}")]
        for c in cats
    ])


def build_metodos_keyboard(prefix: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(m, callback_data=f"{prefix}{m}")]
        for m in METODOS_PAGO
    ])


# ============================================================
#                         COMANDO /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not auth_ok(update):
        msg = update.message or update.callback_query.message
        await msg.reply_text("No tienes permiso para usar este bot.")
        return

    # msg siempre será un Message válido, venga del comando o de un botón
    msg = update.message or update.callback_query.message

    keyboard = [
        [InlineKeyboardButton("📊 Ver datos", callback_data="menu_datos")],
        [InlineKeyboardButton("➖ Registrar Gasto", callback_data="menu_gasto")],
        [InlineKeyboardButton("➕ Registrar Ingreso", callback_data="menu_ingreso")],
        [InlineKeyboardButton("⚙ Programados", callback_data="menu_programados")],
    ]

    await msg.reply_text(
        "Menú principal:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )



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

    # ----------------------------------------------------
    #                 VOLVER AL MENÚ PRINCIPAL
    # ----------------------------------------------------
    if data == "menu_main":
        await start(update, context)
        return
    
    # ----------------------------------------------------
    #                    MENÚ VER DATOS
    # ----------------------------------------------------
    if data == "menu_datos":
        keyboard = [
            [InlineKeyboardButton("📅 Últimos movimientos", callback_data="vd_ultimos")],
            [InlineKeyboardButton("💸 Total gastos del mes", callback_data="vd_gastos_mes")],
            [InlineKeyboardButton("💰 Total ingresos del mes", callback_data="vd_ingresos_mes")],
            [InlineKeyboardButton("📈 Balance mensual", callback_data="vd_balance")],
        ]
        await query.message.reply_text(
            "¿Qué datos quieres consultar?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ----------------------------------------------------
    #             REGISTRO MANUAL GASTO / INGRESO
    # ----------------------------------------------------
    if data == "menu_gasto":
        USER_STATE[user_id] = {"tipo": "Gasto"}
        await query.message.reply_text(
            "Introduce el importe del gasto:",
            reply_markup=build_main_menu()
        )
        return

    if data == "menu_ingreso":
        USER_STATE[user_id] = {"tipo": "Ingreso"}
        await query.message.reply_text(
            "Introduce el importe del ingreso:",
            reply_markup=build_main_menu()
        )
        return

    # ----------------------------------------------------
    #                   MENÚ PROGRAMADOS
    # ----------------------------------------------------
    if data == "menu_programados":
        keyboard = [
            [InlineKeyboardButton("📊 Ver datos", callback_data="menu_datos")],
            [InlineKeyboardButton("📄 Ver programados", callback_data="prog_ver")],
            [InlineKeyboardButton("➕ Añadir programado", callback_data="prog_add")],
            [InlineKeyboardButton("📝 Editar programado", callback_data="prog_edit")],
            [InlineKeyboardButton("❌ Eliminar programado", callback_data="prog_del")],
        ]
        await query.message.reply_text(
            "Gestión de transacciones programadas:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ----------------------------------------------------
    #                    VER PROGRAMADOS
    # ----------------------------------------------------
    if data == "prog_ver":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay transacciones programadas.")
            return

        texto = "Programados:\n\n"
        for p in PROGRAMADOS:
            texto += (
                f"ID {p['id']} — {p['tipo']} — {p['importe']}€ — Día {p['dia']}\n"
                f"{p['descripcion']} ({p['categoria']} · {p.get('metodo','-')})\n\n"
            )

        await query.message.reply_text(texto, reply_markup=build_main_menu())
        return

    # ----------------------------------------------------
    #                AÑADIR PROGRAMADO (PASO A PASO)
    # ----------------------------------------------------
    if data == "prog_add":
        USER_STATE[user_id] = {"modo": "add_programado", "step": "tipo"}
        keyboard = [[
            InlineKeyboardButton("Gasto", callback_data="addp_tipo_Gasto"),
            InlineKeyboardButton("Ingreso", callback_data="addp_tipo_Ingreso")
        ]]
        await query.message.reply_text(
            "Selecciona tipo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Tipo
    if data.startswith("addp_tipo_"):
        st["tipo"] = data.removeprefix("addp_tipo_")
        st["step"] = "importe"
        USER_STATE[user_id] = st

        await query.message.reply_text(
            "Introduce el importe:",
            reply_markup=build_main_menu(),
        )
        return

    # Categoría
    if data.startswith("addp_cat_"):
        st["categoria"] = data.removeprefix("addp_cat_")
        st["step"] = "metodo"
        USER_STATE[user_id] = st

        await query.message.reply_text(
            "Selecciona método:",
            reply_markup=build_metodos_keyboard("addp_met_")
        )
        return

    # Método
    if data.startswith("addp_met_"):
        st["metodo"] = data.removeprefix("addp_met_")
        st["step"] = "descripcion"
        USER_STATE[user_id] = st

        await query.message.reply_text(
            "Escribe la descripción:",
            reply_markup=build_main_menu(),
        )
        return

    # Día
    if data.startswith("addp_dia_"):
        st["dia"] = int(data.removeprefix("addp_dia_"))
        st["step"] = "confirmar"
        USER_STATE[user_id] = st

        texto = (
            f"Confirma:\n\n"
            f"Tipo: {st['tipo']}\n"
            f"Importe: {st['importe']}€\n"
            f"Categoría: {st['categoria']}\n"
            f"Método: {st['metodo']}\n"
            f"Día: {st['dia']}\n"
            f"Descripción: {st['descripcion']}\n"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Confirmar", callback_data="addp_conf_si")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="addp_conf_no")],
        ]

        await query.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Confirmación
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
        await query.message.reply_text(
            f"Programado añadido (ID {new_id})",
            reply_markup=build_main_menu()
        )
        return

    if data == "addp_conf_no":
        USER_STATE[user_id] = {}
        await query.message.reply_text("Cancelado.", reply_markup=build_main_menu())
        return

    # ----------------------------------------------------
    #                 ELIMINAR PROGRAMADO
    # ----------------------------------------------------
    if data == "prog_del":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay programados para eliminar.")
            return

        kb = [
            [InlineKeyboardButton(f"Eliminar ID {p['id']}", callback_data=f"del_{p['id']}")]
            for p in PROGRAMADOS
        ]
        await query.message.reply_text(
            "Selecciona uno:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("del_"):
        pid = int(data.removeprefix("del_"))
        PROGRAMADOS = [p for p in PROGRAMADOS if p["id"] != pid]
        save_programados(PROGRAMADOS)

        await query.message.reply_text("Eliminado.", reply_markup=build_main_menu())
        return

    # ----------------------------------------------------
    #                  EDITAR PROGRAMADOS
    # ----------------------------------------------------
    if data == "prog_edit":
        if not PROGRAMADOS:
            await query.message.reply_text("No hay programados para editar.")
            return

        kb = [
            [InlineKeyboardButton(f"Editar ID {p['id']}", callback_data=f"edit_sel_{p['id']}")]
            for p in PROGRAMADOS
        ]

        USER_STATE[user_id] = {"modo": "edit_programado", "step": "select"}
        await query.message.reply_text(
            "Selecciona el programado:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("edit_sel_"):
        pid = int(data.removeprefix("edit_sel_"))
        if not find_programado(pid):
            await query.message.reply_text("Programado no encontrado.")
            return

        USER_STATE[user_id] = {
            "modo": "edit_programado",
            "step": "field",
            "edit_id": pid
        }

        kb = [
            [InlineKeyboardButton("Tipo", callback_data="field_tipo")],
            [InlineKeyboardButton("Importe", callback_data="field_importe")],
            [InlineKeyboardButton("Categoría", callback_data="field_categoria")],
            [InlineKeyboardButton("Método", callback_data="field_metodo")],
            [InlineKeyboardButton("Descripción", callback_data="field_desc")],
            [InlineKeyboardButton("Día", callback_data="field_dia")],
        ]

        await query.message.reply_text(
            "¿Qué quieres modificar?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ---- Editar campos ----

    if data.startswith("field_"):
        field = data.removeprefix("field_")
        prog = find_programado(st["edit_id"])

        if field == "tipo":
            kb = [[
                InlineKeyboardButton("Gasto", callback_data="set_tipo_Gasto"),
                InlineKeyboardButton("Ingreso", callback_data="set_tipo_Ingreso"),
            ]]
            USER_STATE[user_id]["step"] = "edit_tipo"
            await query.message.reply_text("Nuevo tipo:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if field == "importe":
            USER_STATE[user_id]["step"] = "edit_importe"
            await query.message.reply_text("Nuevo importe:")
            return

        if field == "categoria":
            USER_STATE[user_id]["step"] = "edit_categoria"
            await query.message.reply_text(
                "Nueva categoría:",
                reply_markup=build_categories_keyboard(prog["tipo"], "set_cat_")
            )
            return

        if field == "metodo":
            USER_STATE[user_id]["step"] = "edit_metodo"
            await query.message.reply_text(
                "Nuevo método:",
                reply_markup=build_metodos_keyboard("set_met_")
            )
            return

        if field == "desc":
            USER_STATE[user_id]["step"] = "edit_desc"
            await query.message.reply_text("Nueva descripción:")
            return

        if field == "dia":
            USER_STATE[user_id]["step"] = "edit_dia"
            await query.message.reply_text(
                "Nuevo día:",
                reply_markup=build_days_keyboard("set_dia_")
            )
            return

    # ---- Establecer tipo ----
    if data.startswith("set_tipo_"):
        prog = find_programado(st["edit_id"])
        prog["tipo"] = data.removeprefix("set_tipo_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Tipo actualizado.", reply_markup=build_main_menu())
        return

    # ---- Establecer categoría ----
    if data.startswith("set_cat_"):
        prog = find_programado(st["edit_id"])
        prog["categoria"] = data.removeprefix("set_cat_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Categoría actualizada.", reply_markup=build_main_menu())
        return

    # ---- Establecer método ----
    if data.startswith("set_met_"):
        prog = find_programado(st["edit_id"])
        prog["metodo"] = data.removeprefix("set_met_")
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Método actualizado.", reply_markup=build_main_menu())
        return

    # ---- Establecer día ----
    if data.startswith("set_dia_"):
        prog = find_programado(st["edit_id"])
        prog["dia"] = int(data.removeprefix("set_dia_"))
        save_programados(PROGRAMADOS)
        USER_STATE[user_id] = {}
        await query.message.reply_text("Día actualizado.", reply_markup=build_main_menu())
        return
    # ----------------------------------------------------
    #          REGISTRO NORMAL: CATEGORÍA / MÉTODO / CONFIRMAR
    # ----------------------------------------------------

    # Selección de categoría en un gasto/ingreso normal (NO programado)
    if data.startswith("cat_"):
        categoria = data.removeprefix("cat_")
        if user_id not in USER_STATE:
            return

        USER_STATE[user_id]["categoria"] = categoria

        await query.message.reply_text(
            "Selecciona el método de pago:",
            reply_markup=build_metodos_keyboard("met_")
        )
        return

    # Selección de método de pago en un gasto/ingreso normal
    if data.startswith("met_"):
        metodo = data.removeprefix("met_")
        st = USER_STATE.get(user_id, {})
        if not st:
            return

        st["metodo"] = metodo
        USER_STATE[user_id] = st

        descripcion = f"{st['categoria']} · {metodo}"
        st["descripcion"] = descripcion

        texto = (
            "Confirma el movimiento:\n\n"
            f"Tipo: {st['tipo']}\n"
            f"Importe: {st['importe']} €\n"
            f"Categoría: {st['categoria']}\n"
            f"Método: {st['metodo']}\n"
            f"Descripción: {st['descripcion']}\n"
            f"Fecha: hoy"
        )

        kb = [
            [InlineKeyboardButton("✅ Confirmar", callback_data="conf_si")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="conf_no")],
        ]

        await query.message.reply_text(
            texto,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Confirmar movimiento normal
    if data == "conf_si":
        st = USER_STATE.get(user_id, {})
        if not st:
            return

        hoy = date.today()
        desc = st.get("descripcion", "")
        cat = st.get("categoria", "")
        importe = st.get("importe", 0)

        if st.get("tipo") == "Gasto":
            add_gasto(hoy, importe, desc, cat)
        else:
            add_ingreso(hoy, importe, desc, cat)

        USER_STATE[user_id] = {}
        await query.message.reply_text(
            "Movimiento guardado correctamente ✅",
            reply_markup=build_main_menu()
        )
        return

    # Cancelar movimiento normal
    if data == "conf_no":
        USER_STATE[user_id] = {}
        await query.message.reply_text(
            "Movimiento cancelado.",
            reply_markup=build_main_menu()
        )
        return

    # ----------------------------------------------------
    #               SHOW TEXT HANDLER FALLBACK
    # ----------------------------------------------------
    if data == "vd_ultimos":
        gastos, ingresos = leer_transacciones()

        texto = "📅 *Últimos movimientos*\n\n"

        ult = []

        for g in gastos[-5:]:
            fecha, importe, desc, cat = g
            ult.append(f"🟥 Gasto | {fecha} | {importe}€ | {desc} ({cat})")

        for i in ingresos[-5:]:
            fecha, importe, desc, cat = i
            ult.append(f"🟩 Ingreso | {fecha} | {importe}€ | {desc} ({cat})")

        ult = ult[-10:]  # máximo 10

        await query.message.reply_text("\n".join(ult), reply_markup=build_main_menu())
        return
    
    if data == "vd_gastos_mes":
        gastos, _ = leer_transacciones()
        hoy = date.today()
        total = 0

        for g in gastos:
            fecha = g[0]
            if fecha.startswith(f"{hoy.year}-") and fecha[5:7] == f"{hoy.month:02d}":
                total += float(g[1])

        await query.message.reply_text(
            f"💸 *Gastos del mes*: {total:.2f}€",
            reply_markup=build_main_menu()
        )
        return
    if data == "vd_ingresos_mes":
        _, ingresos = leer_transacciones()
        hoy = date.today()
        total = 0

        for i in ingresos:
            fecha = i[0]
            if fecha.startswith(f"{hoy.year}-") and fecha[5:7] == f"{hoy.month:02d}":
                total += float(i[1])

        await query.message.reply_text(
            f"💰 *Ingresos del mes*: {total:.2f}€",
            reply_markup=build_main_menu()
        )
        return
    if data == "vd_balance":
        gastos, ingresos = leer_transacciones()
        hoy = date.today()

        tg = 0
        ti = 0

        for g in gastos:
            fecha = g[0]
            if fecha.startswith(f"{hoy.year}-") and fecha[5:7] == f"{hoy.month:02d}":
                tg += float(g[1])

        for i in ingresos:
            fecha = i[0]
            if fecha.startswith(f"{hoy.year}-") and fecha[5:7] == f"{hoy.month:02d}":
                ti += float(i[1])

        balance = ti - tg

        await query.message.reply_text(
            f"📈 Balance mensual:\n\n"
            f"💸 Gastos: {tg:.2f}€\n"
            f"💰 Ingresos: {ti:.2f}€\n"
            f"➡ Resultado: *{balance:.2f}€*",
            reply_markup=build_main_menu()
        )
        return
    

# ============================================================
#                     TEXT HANDLER (importe, descripción)
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not auth_ok(update):
        return

    st = USER_STATE.get(user_id, {})

    if not st:
        await update.message.reply_text("Escribe /start para comenzar.")
        return

    # ------------ AÑADIR PROGRAMADO ------------
    if st.get("modo") == "add_programado":
        step = st["step"]

        # Importe
        if step == "importe":
            try:
                st["importe"] = float(text.replace(",", "."))
            except:
                await update.message.reply_text("Importe no válido.", reply_markup=build_main_menu())
                return

            st["step"] = "categoria"
            USER_STATE[user_id] = st
            await update.message.reply_text(
                "Selecciona categoría:",
                reply_markup=build_categories_keyboard(st["tipo"], "addp_cat_")
            )
            return

        # Descripción
        if step == "descripcion":
            st["descripcion"] = text
            st["step"] = "dia"
            USER_STATE[user_id] = st

            await update.message.reply_text(
                "Selecciona el día:",
                reply_markup=build_days_keyboard("addp_dia_")
            )
            return

    # ------------ EDITAR PROGRAMADO ------------
    if st.get("modo") == "edit_programado":
        prog = find_programado(st["edit_id"])

        # Editar importe
        if st["step"] == "edit_importe":
            try:
                prog["importe"] = float(text.replace(",", "."))
            except:
                await update.message.reply_text("Importe no válido.")
                return

            save_programados(PROGRAMADOS)
            USER_STATE[user_id] = {}
            await update.message.reply_text("Importe actualizado.", reply_markup=build_main_menu())
            return

        # Editar descripción
        if st["step"] == "edit_desc":
            prog["descripcion"] = text
            save_programados(PROGRAMADOS)

            USER_STATE[user_id] = {}
            await update.message.reply_text("Descripción actualizada.", reply_markup=build_main_menu())
            return

    # ------------ REGISTRO NORMAL ------------
    if "importe" not in st:
        try:
            st["importe"] = float(text.replace(",", "."))
        except:
            await update.message.reply_text("Importe no válido.")
            return

        categorias = EXPENSE_CATEGORIES if st["tipo"] == "Gasto" else INCOME_CATEGORIES

        kb = [
            [InlineKeyboardButton(c, callback_data=f"cat_{c}")]
            for c in categorias
        ]

        USER_STATE[user_id] = st

        await update.message.reply_text(
            "Selecciona categoría:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return


# ============================================================
#                EJECUCIÓN DIARIA PROGRAMADOS
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

@app_flask.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "Ok", 200


def main():
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Jobs
    job_queue = application.job_queue
    job_queue.run_daily(ejecutar_programados, time(7, 0))

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # ACTIVA EL WEBHOOK
    application.bot.delete_webhook()
    application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    print("Webhook activo:", f"{WEBHOOK_URL}/webhook")

    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
