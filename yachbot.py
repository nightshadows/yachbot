#! /usr/bin/env python
# -*- coding: utf-8 -*-

import collections
import hashlib
import json
import leveldb
import logging
import optparse
import requests
import sys
import telegram

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

YachBotConfiguration = collections.namedtuple("YachBotConfiguration", "db_location token")
def read_configuration(configuration_file):
    from ConfigParser import ConfigParser
    cp = ConfigParser()
    if configuration_file in cp.read([configuration_file]):
        db_location = cp.get("bot", "db_dir")
        token = cp.get("bot", "telegram_token")
        return YachBotConfiguration(db_location, token)

CONFIG = read_configuration("./yachbot.cfg")
DB = leveldb.LevelDB(CONFIG.db_location)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

def ParseArgs():
    parser = optparse.OptionParser()
    return parser.parse_args()

#######################################
#
# database keys:
## size_{room_id} - number of messages in room
## chat_{chat_id} - current room for given companion
## room_{room_nm} - list (space separated) of listeners for room
## message_{index}_{room_id} - message #index in specific room
#
#######################################

def log_info(text):
    logger.warn(text)

def getRoomHistorySize(room_id):
    room_size = "size_%s" % room_id
    try:
        return int(DB.Get(room_size))
    except:
        return 0

def incRoomHistorySize(room_id):
    room_size = "size_%s" % room_id
    try:
        rs = getRoomHistorySize(room_id)
        DB.Put(room_size, str(rs + 1))
    except:
        pass

def getRoomByChat(update):
    try:
        chat_name = "chat_%d" % update.message.chat_id
        return DB.Get(chat_name)
    except:
        return None

def getChatsByRoom(room_name):
    try:
        return DB.Get(room_name).split()
    except:
        return []

def room(bot, update):
    if update.message.text == "/room":
        try:
            bot.sendMessage(update.message.chat_id, text="Please specify the /room name")
        except:
            pass
        return

    room_name = "room_%s" % update.message.text
    chat_name = "chat_%d" % update.message.chat_id

    try:
        chat_idx = DB.Get(room_name).split()
    except:
        chat_idx = []

    if update.message.chat_id in chat_idx:
        return

    exitroom(bot, update)
    chat_idx.append(str(update.message.chat_id))
    DB.Put(room_name, ' '.join(chat_idx))
    DB.Put(chat_name, room_name)

    ping(bot, update)

def exitroom(bot, update):
    try:
        chat_name = "chat_%d" % update.message.chat_id
        room_name = DB.Get(chat_name)
        DB.Delete(chat_name)
        chat_idx = DB.Get(room_name).split()
        chat_idx.remove(str(update.message.chat_id))
        DB.Put(room_name, ' '.join(chat_idx))
    except:
        pass

def helpcommand(bot, update):
    txt = "Anonymous bot. To enter the channel use '/room <channel name>; To leave the channel '/exit'; To show the current channel name '/ping'."
    try:
        bot.sendMessage(update.message.chat_id, txt)
    except:
        error(bot, update, "Help")

def ping(bot, update):
    try:
        room_id = getRoomByChat(update)

        if room_id == None:
            bot.sendMessage(update.message.chat_id, text="No channel, use '/room <channel name>' command to enter one")
            return

        chat_idx = getChatsByRoom(room_id)

        bot.sendMessage(update.message.chat_id, text="Channel %s, %d users here, history size is %d" % (room_id[11:], len(chat_idx), getRoomHistorySize(room_id)))
    except:
        error(bot, update, "Ping")

def echo(bot, update):
    # get the room from the sending user, send message to all users in that room
    room_id = getRoomByChat(update)

    if room_id == None:
        update.message.text = "/room yach"
        room(bot, update)
        bot.sendMessage(update.message.chat_id, text="You were sent to room 'yach', use '/room <room name>' command to select another one.")
        return

    rs = getRoomHistorySize(room_id)
    message_text = "#%d: %s" % (rs, update.message.text)

    send_to_sender = False
    zaebalEgg = u'ты заебал'
    if zaebalEgg in message_text:
        message_text = u"СЛУЖЕБНОЕ СООБЩЕНИЕ #%d: Михаил пытался написать текст 'ты заебал'. Как же ты заебал, Михаил!" % rs
        send_to_sender = True

    chat_idx = sorted(set(getChatsByRoom(room_id)))
    for chat_id in chat_idx:
        if (send_to_sender or update.message.chat_id != int(chat_id)) or (room_id == "room_/room test"):
            try:
                if update.message.sticker:
                    bot.sendSticker(int(chat_id), sticker=update.message.sticker.file_id)
                elif update.message.photo:
                    bot.sendPhoto(int(chat_id), photo=update.message.photo[0].file_id)
                else:
                    bot.sendMessage(int(chat_id), text=message_text)
            except:
                pass

    try:
        history_record = "message_%d_%s" % (rs, room_id)
        DB.Put(history_record, message_text.encode('utf-8'))
        incRoomHistorySize(room_id)
    except Exception as e:
        error(bot, update, e.text)

def history(bot, update):
    try:
        room_id = getRoomByChat(update)
        rs = getRoomHistorySize(room_id)

        historysz = 5
        startid = max(0, rs - historysz)
        for mess in range(startid, rs):
            history_record = "message_%d_%s" % (mess, room_id)
            bot.sendMessage(update.message.chat_id, text=DB.Get(history_record).decode('utf-8'))
    except:
        error(bot, update, "History")

def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))

def yachbot():
    updater = Updater(CONFIG.token)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("room", room))
    dp.add_handler(CommandHandler("help", helpcommand))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("history", history))
    dp.add_handler(CommandHandler("exit", exitroom))
    dp.add_handler(MessageHandler(filters=False, callback=echo))
    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    opt, args = ParseArgs()
    yachbot()
