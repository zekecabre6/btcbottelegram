import asyncio
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler
import os
from dotenv import load_dotenv

load_dotenv()  # Carga las variables de entorno desde el archivo .env
TOKEN = os.getenv("BOT_TOKEN")  # Obtiene el token desde la variable de entorno

# Función para obtener el precio de BTC/USDT desde la API de CoinGecko
def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    response = requests.get(url)
    data = response.json()
    return float(data['bitcoin']['usd'])

# Diccionario para almacenar los intervalos y alertas de cada usuario
user_settings = {}
# Diccionario para rastrear los últimos 10 mensajes enviados por cada chat
last_messages = {}

# Función de inicio del bot
async def start(update, context):
    chat_id = update.effective_chat.id
    await update.message.reply_text("Hola, estoy siguiendo el precio de BTC/USDT para ti. 🚀")
    
    # Agregar el trabajo para enviar el precio periódicamente
    context.job_queue.run_repeating(
        send_btc_price,  # Función que se ejecutará
        interval=60,  # Intervalo en segundos
        first=0,  # Inicia inmediatamente
        chat_id=chat_id  # Pasar el chat_id como dato al contexto del trabajo
    )

# Modificar send_btc_price para obtener chat_id desde el contexto
async def send_btc_price(context):
    chat_id = context.job.chat_id  # Obtén el chat_id del trabajo
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

# Comando para configurar el intervalo de notificaciones
async def set_interval(update: Update, context):
    chat_id = update.message.chat_id
    try:
        # Obtener el nuevo intervalo de la entrada del usuario
        interval = int(context.args[0])
        if interval < 1:
            raise ValueError("El intervalo debe ser al menos de 1 minuto.")
        
        # Eliminar trabajos anteriores para este usuario
        current_jobs = context.job_queue.get_jobs_by_name(chat_id)
        for job in current_jobs:
            job.schedule_removal()  # Remueve la tarea anterior

        # Configurar el nuevo intervalo en el diccionario de usuario
        user_settings[chat_id]["interval"] = interval * 60
        
        # Crear la nueva tarea periódica con el nuevo intervalo
        context.job_queue.run_repeating(send_btc_price, interval=interval * 60, first=0, chat_id=chat_id)
        
        # Responder al usuario
        await update.message.reply_text(f"⏱ Intervalo de notificaciones actualizado a {interval} minutos.")
    
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Por favor, proporciona un número válido de minutos. Ejemplo: /setinterval 60")

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
    current_jobs = context.job_queue.get_jobs_by_name(chat_id)
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

# Función asincrónica para realizar peticiones constantes
async def fetch_prices_forever():
    while True:
        try:
            price = get_btc_price()  # Obtiene el precio
            print(f"Precio actual de BTC/USDT: ${price:.2f}")  # Opcional: imprimir en consola
        except Exception as e:
            print(f"Error al obtener el precio: {e}")
        await asyncio.sleep(5)  # Espera 5 segundos antes de la siguiente petición

# Inicializa el bot y las peticiones constantes
async def main():
    application = Application.builder().token(TOKEN).build()

    if not application.job_queue:
        print("JobQueue no está configurado.")
    else:
        # Manejadores de comandos
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('setinterval', set_interval))
        application.add_handler(CommandHandler('alert', set_alert))
        application.add_handler(CommandHandler('stop', stop))

        # Inicia el bot y la tarea de peticiones constantes
        tasks = asyncio.gather(application.run_polling(), fetch_prices_forever())
        await tasks

# Si ya hay un bucle de eventos en ejecución, evita llamar a asyncio.run
if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()  # Permite usar un bucle de eventos dentro de otro
    asyncio.run(main())  # Ejecuta la corutina 'main'
