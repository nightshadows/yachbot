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

Bans = {}
BAN_DURATION = 10

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

def getCommentNumberForReply(update):
    try:
        reply = update.message.reply_to_message
        if not reply:
            return None

        comment_number = int(reply.text[1:reply.text.find(':')])
        return comment_number
    except:
        return None

def getReplyByChat(update):
    try:
        room_id = getRoomByChat(update)
        comment_number = getCommentNumberForReply(update)
        if not comment_number:
            return {}

        msg_list_record = "mid_%s_%s" % (comment_number, room_id)
        msg_idx = DB.Get(msg_list_record).split()
        result = {}
        for msg in msg_idx:
            ch_id, msg_id = msg.split(':')
            result[ch_id] = int(msg_id)

        return result
    except:
        return {}

def startcommand(bot, update):
    # do nothing, this is just to supress "/start" messages in the chat
    pass

def ban(bot, update):
    try:
        room_id = getRoomByChat(update)
        rs = getRoomHistorySize(room_id)
        mid = int(update.message.text[5:])
        uid_record = "uid_%d_%s" % (mid, room_id)
        uid = int(DB.Get(uid_record))
        if not room_id in Bans:
            Bans[room_id] = {}
        Bans[room_id][uid] = mid + BAN_DURATION
        print "User is banned in %s till %d" % (room_id, Bans[room_id][uid])
    except:
        print "Ban error"
        pass

def is_banned(update):
    try:
        room_id = getRoomByChat(update)
        rs = getRoomHistorySize(room_id)
        uid = update.message.chat_id
        ban_val = Bans[room_id][uid]
        if ban_val > rs:
            return [True, ban_val]
    except:
        pass
    return [False, 0]

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

def deletecommand(bot, update, args):
    try:
        room_id = getRoomByChat(update)
        comment_number = args[0]
        msg_list_record = "mid_%s_%s" % (comment_number, room_id)
        msg_idx = DB.Get(msg_list_record).split()
        for msg in msg_idx:
            ch_id, msg_id = msg.split(':')
            try:
                bot.editMessageText(chat_id=int(ch_id), message_id=int(msg_id), text=u"РосКомНадзор")
            except Exception as e:
                print e
    except:
        pass

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

def get_comment_number_text(number):
    if number != None:
        return "#%d: " % number
    return "None"

def echo(bot, update):
    # get the room from the sending user, send message to all users in that room
    room_id = getRoomByChat(update)

    if room_id == None:
        update.message.text = "/room yach"
        room(bot, update)
        try:
            bot.sendMessage(update.message.chat_id, text="You were sent to room 'yach', use '/room <room name>' command to select another one.")
        except:
            pass
        return

    rs = getRoomHistorySize(room_id)
    message_text = get_comment_number_text(rs) + update.message.text

    no_history = False
    banned = is_banned(update)
    if banned[0]:
        message_text = "User tried to write something, but he is banned for %d messages" % BAN_DURATION
        try:
            bot.sendMessage(update.message.chat_id, text="You are banned till %d" % banned[1])
        except:
            pass
        no_history = True

    send_to_sender = False
    chat_idx = sorted(set(getChatsByRoom(room_id)))
    msg_idx = []
    reply_dict = getReplyByChat(update)
    reply_number = getCommentNumberForReply(update)

    for chat_id in chat_idx:
        kwargs = {}
        if chat_id in reply_dict:
            kwargs['reply_to_message_id'] = reply_dict[chat_id]

        if (send_to_sender or update.message.chat_id != int(chat_id)) or (room_id == "room_/room test"):
            try:
                if update.message.sticker:
                    r = bot.sendSticker(int(chat_id), sticker=update.message.sticker.file_id, **kwargs)
                    try:
                        msg_idx.append("%d:%d" % (r.chat.id, r.message_id))
                    except:
                        pass
                elif update.message.photo:
                    r = bot.sendPhoto(int(chat_id), photo=update.message.photo[0].file_id, **kwargs)
                    try:
                        msg_idx.append("%d:%d" % (r.chat.id, r.message_id))
                    except:
                        pass
                elif update.message.document:
                    r = bot.sendDocument(int(chat_id), document=update.message.document.file_id, **kwargs)
                    try:
                        msg_idx.append("%d:%d" % (r.chat.id, r.message_id))
                    except:
                        pass
                elif update.message.video:
                    r = bot.sendVideo(int(chat_id), document=update.message.video.file_id, **kwargs)
                    try:
                        msg_idx.append("%d:%d" % (r.chat.id, r.message_id))
                    except:
                        pass
                else:
                    r = bot.sendMessage(int(chat_id), text=message_text, **kwargs)
                    try:
                        msg_idx.append("%d:%d" % (r.chat.id, r.message_id))
                    except:
                        pass
            except:
                pass

    if not no_history:
        try:
            history_record = "message_%d_%s" % (rs, room_id)
            DB.Put(history_record, message_text.encode('utf-8'))
            uid_record = "uid_%d_%s" % (rs, room_id)
            DB.Put(uid_record, str(update.message.chat_id))

            message_record = "mid_%d_%s" % (rs, room_id)
            print "Message %d was sent to %s, received by %d users" % (rs, room_id, len(msg_idx))
            DB.Put(message_record, ' '.join(msg_idx))

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
    dp.add_handler(CommandHandler("start", startcommand))
    dp.add_handler(CommandHandler("help", helpcommand))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("history", history))
    dp.add_handler(CommandHandler("exit", exitroom))
    dp.add_handler(CommandHandler("ban", ban))
    dp.add_handler(CommandHandler("delete", deletecommand, pass_args=True))
    dp.add_handler(MessageHandler(filters=False, callback=echo))
    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    opt, args = ParseArgs()
    yachbot()
