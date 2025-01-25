import asyncio
import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler
import os
TOKEN = os.getenv("BOT_TOKEN")


# Función para obtener el precio de BTC/USDT desde la API de Binance
def get_btc_price():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    response = requests.get(url)
    data = response.json()
    return float(data['price'])

# Diccionario para almacenar los intervalos y alertas de cada usuario
user_settings = {}
# Diccionario para rastrear los últimos 10 mensajes enviados por cada chat
last_messages = {}

async def send_btc_price(context):
    chat_id = context.job.chat_id
    price = get_btc_price()

    # Envía un nuevo mensaje con el precio
    message = await context.bot.send_message(chat_id=chat_id, text=f"💰 El precio actual de BTC/USDT es: ${price:.2f}")

    # Almacena el ID del mensaje enviado
    if chat_id not in last_messages:
        last_messages[chat_id] = []
    last_messages[chat_id].append(message.message_id)

    # Si hay más de 10 mensajes, elimina todos los mensajes
    if len(last_messages[chat_id]) > 10:
        for message_id in last_messages[chat_id]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                print(f"No se pudo eliminar el mensaje: {e}")
        last_messages[chat_id] = []  # Limpia la lista de mensajes después de borrarlos

    # Verifica alertas de precios configuradas
    user_data = user_settings.get(chat_id, {})
    alert_above = user_data.get("alert_above")
    alert_below = user_data.get("alert_below")
    if alert_above and price > alert_above:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ El precio ha superado tu alerta: ${alert_above:.2f}")
        user_data["alert_above"] = None  # Resetea la alerta después de notificar
    if alert_below and price < alert_below:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ El precio ha bajado de tu alerta: ${alert_below:.2f}")
        user_data["alert_below"] = None  # Resetea la alerta después de notificar

# Comando de inicio
async def start(update: Update, context):
    chat_id = update.message.chat_id

    # Configuración inicial del usuario
    user_settings[chat_id] = {"interval": 60, "alert_above": None, "alert_below": None}

    # Mensaje de bienvenida con menú
    menu = ReplyKeyboardMarkup(
        [["📈 Precio cada minuto", "⏱ Cambiar intervalo"], ["🔔 Configurar alerta"]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "👋 ¡Hola! Bienvenido al bot de seguimiento de precios de BTC/USDT. Aquí están tus opciones: \n\n"
        "📈 *Precio cada minuto*: Recibe el precio automáticamente.\n"
        "⏱ *Cambiar intervalo*: Ajusta la frecuencia de notificaciones. Ejemplo: /setinterval 5\n"
        "🔔 *Configurar alerta*: Configura alertas personalizadas cuando el precio suba o baje. Ejemplo: /alert arriba 104000\n\n"
        "Por defecto, recibirás actualizaciones cada 1 minuto. 🎯",
        reply_markup=menu,
        parse_mode="Markdown"
    )

    # Inicia el envío periódico de precios
    context.job_queue.run_repeating(send_btc_price, interval=60, first=0, chat_id=chat_id)

# Comando para configurar el intervalo de notificaciones
async def set_interval(update: Update, context):
    chat_id = update.message.chat_id
    try:
        # Obtener el nuevo intervalo de la entrada del usuario
        interval = int(context.args[0])
        if interval < 1:
            raise ValueError("El intervalo debe ser al menos de 1 minuto.")
        
        # Eliminar trabajos anteriores para este usuario
        current_jobs = context.job_queue.get_jobs_by_chat_id(chat_id)
        for job in current_jobs:
            job.schedule_removal()  # Remueve la tarea anterior

        # Configurar el nuevo intervalo en el diccionario de usuario
        user_settings[chat_id]["interval"] = interval * 60
        
        # Crear la nueva tarea periódica con el nuevo intervalo
        context.job_queue.run_repeating(send_btc_price, interval=interval * 60, first=0, chat_id=chat_id)
        
        # Responder al usuario
        await update.message.reply_text(f"⏱ Intervalo de notificaciones actualizado a {interval} minutos.")
    
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Por favor, proporciona un número válido de minutos. Ejemplo: /setinterval 5")

# Comando para configurar alertas de precios
async def set_alert(update: Update, context):
    chat_id = update.message.chat_id
    try:
        direction = context.args[0].lower()
        price = float(context.args[1])
        if direction == "arriba":
            user_settings[chat_id]["alert_above"] = price
            await update.message.reply_text(f"🔔 Alerta configurada: Te avisaré si el precio sube por encima de ${price:.2f}.")
        elif direction == "abajo":
            user_settings[chat_id]["alert_below"] = price
            await update.message.reply_text(f"🔔 Alerta configurada: Te avisaré si el precio baja por debajo de ${price:.2f}.")
        else:
            raise ValueError("Dirección inválida. Usa 'arriba' o 'abajo'.")
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Uso incorrecto. Ejemplo: /alert arriba 106000 o /alert abajo 103000")

# Comando para detener el bot
async def stop(update: Update, context):
    chat_id = update.message.chat_id

    # Detener el envío de precios periódicos
    current_jobs = context.job_queue.get_jobs_by_chat_id(chat_id)
    for job in current_jobs:
        job.schedule_removal()  # Remueve la tarea periódica

    # Elimina los mensajes almacenados
    if chat_id in last_messages:
        for message_id in last_messages[chat_id]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                print(f"No se pudo eliminar un mensaje: {e}")
        del last_messages[chat_id]

    await update.message.reply_text("🔴 El bot ha sido detenido. Ya no recibirás actualizaciones de precios.")

# Inicializa el bot
async def main():
    application = Application.builder().token(TOKEN).build()

    # Manejadores de comandos
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('setinterval', set_interval))
    application.add_handler(CommandHandler('alert', set_alert))
    application.add_handler(CommandHandler('stop', stop))

    # Inicia el bot
    await application.run_polling()

# Si ya hay un bucle de eventos en ejecución, evita llamar a asyncio.run
if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()  # Permite usar un bucle de eventos dentro de otro
    asyncio.run(main())  # Ejecuta la corutina 'main'
