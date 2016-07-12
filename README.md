# yachbot
yachbot

## How to run
pip2 install python-telegram-bot  
pip2 install leveldb  
touch yachbot.cfg # and fill [bot] section with parameters: **db\_dir** and **telegram\_token**  
python2 yachbot.py 


## Configuration file format
Here is minimal content of *yachbot.cfg*: <pre>
[bot]
db_dir = ./yachdb
telegram_token = very-secret-token
</pre>
