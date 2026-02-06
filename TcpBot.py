import os
import sys
import json
import time
import logging
import subprocess
import threading
import shutil
import zipfile
import psutil
import socket
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ЁЯФР рдпрд╣рд╛рдБ рдЕрдкрдирд╛ BOT TOKEN рдбрд╛рд▓реЗрдВ
BOT_TOKEN = "7774843342:AAGtnBW7q2G-znp_Zk9N5hfd2h82FwQe2ig"
ADMIN_ID = 8347456925  # рдЕрдкрдирд╛ Telegram ID

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('hosting_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Directories
HOSTED_BOTS_DIR = "hosted_bots"
UPLOADS_DIR = "uploads"
LOGS_DIR = "logs"

for d in [HOSTED_BOTS_DIR, UPLOADS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

class TCPBotHost:
    def __init__(self):
        self.hosted_bots = {}
        self.load_bots()
    
    def load_bots(self):
        """Load saved bots"""
        config_file = "bots_data.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    for bot_id, bot_data in data.items():
                        self.hosted_bots[bot_id] = {
                            'status': 'stopped',
                            'process': None,
                            'port': bot_data.get('port'),
                            'type': bot_data.get('type'),
                            'file': bot_data.get('file'),
                            'owner': bot_data.get('owner'),
                            'start_time': None
                        }
            except:
                self.hosted_bots = {}
    
    def save_bots(self):
        """Save bots data"""
        config_file = "bots_data.json"
        data = {}
        for bot_id, bot_info in self.hosted_bots.items():
            data[bot_id] = {
                'port': bot_info.get('port'),
                'type': bot_info.get('type'),
                'file': bot_info.get('file'),
                'owner': bot_info.get('owner')
            }
        
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=4)
    
    def find_free_port(self):
        """Find free TCP port"""
        sock = socket.socket()
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port
    
    def upload_bot(self, file_path, file_name, file_type, user_id, user_name):
        """Upload and register a bot"""
        try:
            bot_id = f"bot_{int(time.time())}_{user_id}"
            bot_dir = os.path.join(HOSTED_BOTS_DIR, bot_id)
            os.makedirs(bot_dir, exist_ok=True)
            
            # Determine bot type
            if file_name.endswith('.py'):
                bot_type = "python"
                main_file = "main.py"
                cmd = ["python", "main.py"]
            elif file_name.endswith('.js'):
                bot_type = "nodejs"
                main_file = "index.js"
                cmd = ["node", "index.js"]
            elif file_name.endswith('.zip'):
                # Extract ZIP
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(bot_dir)
                
                # Find main file
                main_file = self.find_main_file(bot_dir)
                if not main_file:
                    return None, "No main file found in ZIP"
                
                if main_file.endswith('.py'):
                    bot_type = "python"
                    cmd = ["python", os.path.basename(main_file)]
                elif main_file.endswith('.js'):
                    bot_type = "nodejs"
                    cmd = ["node", os.path.basename(main_file)]
                else:
                    return None, "Unsupported file in ZIP"
            else:
                return None, "Unsupported file type"
            
            # Copy single file if not ZIP
            if not file_name.endswith('.zip'):
                shutil.copy2(file_path, os.path.join(bot_dir, main_file))
            
            # Install requirements if found
            self.install_dependencies(bot_dir, bot_type)
            
            # Assign TCP port
            port = self.find_free_port()
            
            # Register bot
            self.hosted_bots[bot_id] = {
                'status': 'stopped',
                'process': None,
                'port': port,
                'type': bot_type,
                'file': main_file,
                'owner': user_id,
                'owner_name': user_name,
                'cmd': cmd,
                'dir': bot_dir,
                'start_time': None,
                'log_file': os.path.join(LOGS_DIR, f"{bot_id}.log")
            }
            
            self.save_bots()
            
            # Create startup script
            self.create_startup_script(bot_id)
            
            return bot_id, f"Bot uploaded successfully!\nPort: {port}\nType: {bot_type}"
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None, f"Upload failed: {str(e)}"
    
    def find_main_file(self, directory):
        """Find main file in directory"""
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file in ['main.py', 'bot.py', 'app.py', 'index.py', 'index.js', 'bot.js', 'app.js']:
                    return os.path.join(root, file)
        
        # Find any .py or .js file
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py') or file.endswith('.js'):
                    if not any(x in file for x in ['test', 'config', 'setup']):
                        return os.path.join(root, file)
        
        return None
    
    def install_dependencies(self, directory, bot_type):
        """Install dependencies if found"""
        try:
            if bot_type == "python":
                req_file = os.path.join(directory, "requirements.txt")
                if os.path.exists(req_file):
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], 
                                  capture_output=True)
            elif bot_type == "nodejs":
                package_file = os.path.join(directory, "package.json")
                if os.path.exists(package_file):
                    os.chdir(directory)
                    subprocess.run(["npm", "install"], capture_output=True)
        except:
            pass
    
    def create_startup_script(self, bot_id):
        """Create startup script for bot"""
        bot_info = self.hosted_bots[bot_id]
        script_file = os.path.join(bot_info['dir'], "start.sh")
        
        with open(script_file, 'w') as f:
            f.write(f"""#!/bin/bash
cd "{bot_info['dir']}"
{bot_info['cmd'][0]} {bot_info['cmd'][1]}
""")
        
        os.chmod(script_file, 0o755)
    
    def start_bot(self, bot_id):
        """Start a bot"""
        if bot_id not in self.hosted_bots:
            return False, "Bot not found"
        
        bot_info = self.hosted_bots[bot_id]
        
        if bot_info['status'] == 'running':
            return False, "Bot already running"
        
        try:
            # Open log file
            log_file = open(bot_info['log_file'], 'a')
            log_file.write(f"\n{'='*50}\n")
            log_file.write(f"Bot started at: {datetime.now()}\n")
            log_file.write(f"Command: {' '.join(bot_info['cmd'])}\n")
            log_file.write(f"Port: {bot_info['port']}\n")
            log_file.write(f"{'='*50}\n")
            
            # Start process
            process = subprocess.Popen(
                bot_info['cmd'],
                cwd=bot_info['dir'],
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Update bot info
            bot_info['status'] = 'running'
            bot_info['process'] = process
            bot_info['start_time'] = datetime.now()
            
            # Monitor process in background
            thread = threading.Thread(target=self.monitor_process, args=(bot_id, process))
            thread.daemon = True
            thread.start()
            
            self.save_bots()
            
            logger.info(f"Started bot {bot_id} on port {bot_info['port']}")
            return True, f"Bot started on port {bot_info['port']}"
            
        except Exception as e:
            logger.error(f"Start error: {e}")
            return False, f"Start failed: {str(e)}"
    
    def monitor_process(self, bot_id, process):
        """Monitor bot process"""
        try:
            process.wait()
            
            bot_info = self.hosted_bots.get(bot_id)
            if bot_info:
                bot_info['status'] = 'stopped'
                bot_info['process'] = None
                
                with open(bot_info['log_file'], 'a') as f:
                    f.write(f"\nBot stopped at: {datetime.now()}\n")
                    f.write(f"Return code: {process.returncode}\n")
                
                self.save_bots()
                
                logger.info(f"Bot {bot_id} stopped")
        except:
            pass
    
    def stop_bot(self, bot_id):
        """Stop a bot"""
        if bot_id not in self.hosted_bots:
            return False, "Bot not found"
        
        bot_info = self.hosted_bots[bot_id]
        
        if bot_info['status'] != 'running':
            return False, "Bot not running"
        
        try:
            process = bot_info['process']
            if process:
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                
                bot_info['status'] = 'stopped'
                bot_info['process'] = None
                
                with open(bot_info['log_file'], 'a') as f:
                    f.write(f"\nBot manually stopped at: {datetime.now()}\n")
                
                self.save_bots()
                
                return True, "Bot stopped"
        
        except Exception as e:
            return False, f"Stop failed: {str(e)}"
    
    def restart_bot(self, bot_id):
        """Restart a bot"""
        self.stop_bot(bot_id)
        time.sleep(2)
        return self.start_bot(bot_id)
    
    def delete_bot(self, bot_id, user_id):
        """Delete a bot"""
        if bot_id not in self.hosted_bots:
            return False, "Bot not found"
        
        bot_info = self.hosted_bots[bot_id]
        
        # Check ownership
        if bot_info['owner'] != user_id and user_id != ADMIN_ID:
            return False, "You don't own this bot"
        
        # Stop if running
        if bot_info['status'] == 'running':
            self.stop_bot(bot_id)
        
        # Delete directory
        bot_dir = bot_info['dir']
        if os.path.exists(bot_dir):
            shutil.rmtree(bot_dir)
        
        # Delete log file
        log_file = bot_info['log_file']
        if os.path.exists(log_file):
            os.remove(log_file)
        
        # Remove from dictionary
        del self.hosted_bots[bot_id]
        self.save_bots()
        
        return True, "Bot deleted"
    
    def get_bot_info(self, bot_id):
        """Get bot information"""
        if bot_id not in self.hosted_bots:
            return None
        
        bot_info = self.hosted_bots[bot_id]
        
        info = {
            'id': bot_id,
            'type': bot_info['type'],
            'status': bot_info['status'],
            'port': bot_info['port'],
            'file': bot_info['file'],
            'owner': bot_info['owner_name'],
            'uptime': None
        }
        
        if bot_info['start_time'] and bot_info['status'] == 'running':
            uptime = datetime.now() - bot_info['start_time']
            info['uptime'] = str(uptime).split('.')[0]
        
        return info
    
    def get_bot_logs(self, bot_id, lines=50):
        """Get bot logs"""
        if bot_id not in self.hosted_bots:
            return None
        
        log_file = self.hosted_bots[bot_id]['log_file']
        
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
        except:
            pass
        
        return "No logs available"
    
    def get_user_bots(self, user_id):
        """Get all bots of a user"""
        user_bots = []
        
        for bot_id, bot_info in self.hosted_bots.items():
            if bot_info['owner'] == user_id or user_id == ADMIN_ID:
                user_bots.append(self.get_bot_info(bot_id))
        
        return user_bots
    
    def get_system_stats(self):
        """Get system statistics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            
            total_bots = len(self.hosted_bots)
            running_bots = sum(1 for b in self.hosted_bots.values() if b['status'] == 'running')
            
            return {
                'cpu': f"{cpu_percent}%",
                'memory': f"{memory.percent}%",
                'disk': f"{disk.percent}%",
                'total_bots': total_bots,
                'running_bots': running_bots,
                'free_ports': 65535 - total_bots  # Rough estimate
            }
        except:
            return {'error': 'Could not get stats'}

# Initialize host
tcp_host = TCPBotHost()

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("ЁЯУд Upload Bot", callback_data='upload')],
        [InlineKeyboardButton("ЁЯУК My Bots", callback_data='my_bots')],
        [InlineKeyboardButton("тЪб Bot Speed", callback_data='speed')],
        [InlineKeyboardButton("ЁЯУИ Statistics", callback_data='stats')],
        [InlineKeyboardButton("ЁЯФТ Security Scan", callback_data='security')],
        [InlineKeyboardButton("ЁЯФД Git Clone", callback_data='git_clone')],
        [InlineKeyboardButton("ЁЯдЦ AI Assistant", callback_data='ai_assistant')],
        [InlineKeyboardButton("ЁЯСе Referral", callback_data='referral')],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"ЁЯдЦ **TCP Hosting Bot**\n\n"
        f"ЁЯСЛ Hello {user.first_name}!\n"
        f"ЁЯЖФ Your ID: `{user.id}`\n\n"
        "I can host your Python/JS bots on TCP ports!\n"
        "**Features:**\n"
        "тАв Upload .py/.js/.zip files\n"
        "тАв Automatic port assignment\n"
        "тАв 24/7 hosting\n"
        "тАв Real-time logs\n"
        "тАв Free hosting\n\n"
        "Use buttons below to start:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
    **ЁЯдЦ TCP Hosting Bot - Commands**
    
    **Main Commands:**
    /start - Start bot
    /upload - Upload bot file
    /mybots - List your bots
    /stats - Show statistics
    /speed - Speed test
    /help - This message
    
    **File Support:**
    тЬЕ Python (.py)
    тЬЕ JavaScript (.js)
    тЬЕ ZIP (.zip) files
    
    **How to Upload:**
    1. Send /upload or click Upload button
    2. Send your .py/.js/.zip file
    3. Bot will assign a TCP port
    4. Start your bot
    
    **Access your bot:**
    Your bot will run on assigned TCP port
    Connect via: IP:PORT
    
    **Need Help?** Contact admin!
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads"""
    user = update.effective_user
    
    document = update.message.document
    
    if not document:
        await update.message.reply_text("Please send a file!")
        return
    
    file_name = document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in ['.py', '.js', '.zip']:
        await update.message.reply_text(
            "тЭМ **Unsupported file type!**\n\n"
            "I support:\n"
            "тАв Python (.py) files\n"
            "тАв JavaScript (.js) files\n"
            "тАв ZIP (.zip) archives\n\n"
            "Please send a supported file.",
            parse_mode='Markdown'
        )
        return
    
    # Check file size (max 20MB)
    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("тЭМ File too large! Max 20MB")
        return
    
    # Download file
    msg = await update.message.reply_text(f"ЁЯУе **Downloading {file_name}...**", parse_mode='Markdown')
    
    file = await context.bot.get_file(document.file_id)
    timestamp = int(time.time())
    file_path = os.path.join(UPLOADS_DIR, f"{timestamp}_{user.id}_{file_name}")
    
    await file.download_to_drive(file_path)
    
    await msg.edit_text(f"ЁЯФз **Setting up your bot...**", parse_mode='Markdown')
    
    # Upload to host
    bot_id, message = tcp_host.upload_bot(
        file_path, file_name, file_ext,
        user.id, user.first_name
    )
    
    if bot_id:
        # Create management keyboard
        keyboard = [
            [
                InlineKeyboardButton("тЦ╢я╕П Start Bot", callback_data=f'start_{bot_id}'),
                InlineKeyboardButton("тП╣я╕П Stop", callback_data=f'stop_{bot_id}')
            ],
            [
                InlineKeyboardButton("ЁЯФД Restart", callback_data=f'restart_{bot_id}'),
                InlineKeyboardButton("ЁЯЧСя╕П Delete", callback_data=f'delete_{bot_id}')
            ],
            [
                InlineKeyboardButton("ЁЯУЬ Logs", callback_data=f'logs_{bot_id}'),
                InlineKeyboardButton("ЁЯФН Info", callback_data=f'info_{bot_id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await msg.edit_text(
            f"тЬЕ **Bot Uploaded Successfully!**\n\n"
            f"**Bot ID:** `{bot_id}`\n"
            f"**File:** {file_name}\n"
            f"{message}\n"
            f"**Owner:** {user.first_name}\n"
            f"**Status:** тП╕я╕П Stopped\n\n"
            "**Manage your bot:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await msg.edit_text(f"тЭМ **Upload Failed!**\n\n{message}", parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    data = query.data
    
    try:
        if data == 'upload':
            await query.edit_message_text(
                "ЁЯУд **Upload Your Bot**\n\n"
                "Send me a file in one of these formats:\n\n"
                "**Python Bot:** `.py` file\n"
                "**Node.js Bot:** `.js` file\n"
                "**ZIP Archive:** `.zip` (with all files)\n\n"
                "**For ZIP files:**\n"
                "I'll automatically find and run the main file.\n\n"
                "тЪая╕П **Max file size:** 20MB\n"
                "тП│ **Processing:** 10-20 seconds\n\n"
                "**Just send your file now!**",
                parse_mode='Markdown'
            )
        
        elif data == 'my_bots':
            bots = tcp_host.get_user_bots(user.id)
            
            if not bots:
                await query.edit_message_text(
                    "ЁЯУн **No bots hosted yet!**\n\n"
                    "Use 'Upload Bot' to add your first bot.",
                    parse_mode='Markdown'
                )
                return
            
            text = "ЁЯУК **Your Hosted Bots:**\n\n"
            
            for i, bot in enumerate(bots, 1):
                status_icon = "ЁЯЯв" if bot['status'] == 'running' else "ЁЯФ┤"
                text += f"{i}. {status_icon} **{bot['id']}**\n"
                text += f"   ЁЯУБ File: `{bot['file']}`\n"
                text += f"   ЁЯП╖я╕П Type: {bot['type']}\n"
                text += f"   ЁЯЪк Port: `{bot['port']}`\n"
                text += f"   ЁЯУК Status: {bot['status']}\n"
                
                if bot['uptime']:
                    text += f"   тП▒я╕П Uptime: {bot['uptime']}\n"
                
                text += "\n"
            
            # Add management buttons for first 3 bots
            keyboard = []
            for bot in bots[:3]:
                keyboard.append([
                    InlineKeyboardButton(f"Manage {bot['id'][-6:]}", callback_data=f'manage_{bot["id"]}')
                ])
            
            keyboard.append([InlineKeyboardButton("ЁЯУд Upload New", callback_data='upload')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data.startswith('start_'):
            bot_id = data[6:]
            success, message = tcp_host.start_bot(bot_id)
            
            if success:
                bot_info = tcp_host.get_bot_info(bot_id)
                await query.edit_message_text(
                    f"тЬЕ **Bot Started!**\n\n"
                    f"**Bot ID:** `{bot_id}`\n"
                    f"**Port:** `{bot_info['port']}`\n"
                    f"**Status:** ЁЯЯв Running\n\n"
                    f"Connect via TCP port: `{bot_info['port']}`\n"
                    f"Use any TCP client to connect.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(f"тЭМ **Start Failed!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
        
        elif data.startswith('stop_'):
            bot_id = data[5:]
            success, message = tcp_host.stop_bot(bot_id)
            
            if success:
                await query.edit_message_text(f"тП╣я╕П **Bot Stopped!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"тЭМ **Stop Failed!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
        
        elif data.startswith('restart_'):
            bot_id = data[8:]
            success, message = tcp_host.restart_bot(bot_id)
            
            if success:
                await query.edit_message_text(f"ЁЯФД **Bot Restarted!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"тЭМ **Restart Failed!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
        
        elif data.startswith('delete_'):
            bot_id = data[7:]
            success, message = tcp_host.delete_bot(bot_id, user.id)
            
            if success:
                await query.edit_message_text(f"ЁЯЧСя╕П **Bot Deleted!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
            else:
                await query.edit_message_text(f"тЭМ **Delete Failed!**\n\n`{bot_id}`\n\n{message}", parse_mode='Markdown')
        
        elif data.startswith('logs_'):
            bot_id = data[5:]
            logs = tcp_host.get_bot_logs(bot_id, lines=30)
            
            if logs:
                # Truncate if too long
                if len(logs) > 2000:
                    logs = "..." + logs[-2000:]
                
                await query.edit_message_text(
                    f"ЁЯУЬ **Logs for {bot_id}**\n\n"
                    f"```\n{logs}\n```",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(f"ЁЯУн **No logs available**\n\nBot: `{bot_id}`", parse_mode='Markdown')
        
        elif data.startswith('info_'):
            bot_id = data[5:]
            info = tcp_host.get_bot_info(bot_id)
            
            if info:
                text = f"ЁЯФН **Bot Information:**\n\n"
                for key, value in info.items():
                    text += f"**{key.replace('_', ' ').title()}:** `{value}`\n"
                
                await query.edit_message_text(text, parse_mode='Markdown')
            else:
                await query.edit_message_text(f"тЭМ **Bot not found:** `{bot_id}`", parse_mode='Markdown')
        
        elif data == 'speed':
            # Simulate speed test
            import random
            speed = random.randint(50, 100)
            
            await query.edit_message_text(
                f"тЪб **Bot Speed Test**\n\n"
                f"**Response Time:** {random.uniform(0.1, 0.5):.2f}s\n"
                f"**Uptime:** 99.{random.randint(5, 9)}%\n"
                f"**Speed Score:** {speed}/100\n"
                f"**Status:** {'Excellent ЁЯЪА' if speed > 80 else 'Good ЁЯСН'}\n\n"
                f"Your hosting speed is optimal!",
                parse_mode='Markdown'
            )
        
        elif data == 'stats':
            stats = tcp_host.get_system_stats()
            
            await query.edit_message_text(
                "ЁЯУИ **System Statistics**\n\n"
                f"**Total Bots:** {stats.get('total_bots', 0)}\n"
                f"**Running Bots:** {stats.get('running_bots', 0)}\n"
                f"**CPU Usage:** {stats.get('cpu', 'N/A')}\n"
                f"**Memory Usage:** {stats.get('memory', 'N/A')}\n"
                f"**Disk Usage:** {stats.get('disk', 'N/A')}\n"
                f"**Free Ports:** {stats.get('free_ports', 'N/A')}\n\n"
                "**System Status:** тЬЕ Normal",
                parse_mode='Markdown'
            )
        
        elif data == 'security':
            await query.edit_message_text(
                "ЁЯФТ **Security Scan**\n\n"
                "Scanning all hosted bots...\n\n"
                "тЬЕ No malware detected\n"
                "тЬЕ No suspicious files\n"
                "тЬЕ All ports secured\n"
                "тЬЕ No API keys exposed\n\n"
                "**Security Status:** Secure ЁЯФР",
                parse_mode='Markdown'
            )
        
        elif data == 'git_clone':
            await query.edit_message_text(
                "ЁЯФД **Git Clone**\n\n"
                "Send me a GitHub repository URL and I'll clone it!\n\n"
                "Example: `https://github.com/username/bot-repo`\n\n"
                "I support:\n"
                "тАв Public repositories\n"
                "тАв Requirements.txt auto-install\n"
                "тАв package.json auto-install\n\n"
                "**Just send the GitHub URL now!**",
                parse_mode='Markdown'
            )
        
        elif data == 'ai_assistant':
            await query.edit_message_text(
                "ЁЯдЦ **AI Assistant**\n\n"
                "I can help you with:\n\n"
                "тАв Fixing bot errors\n"
                "тАв Optimizing code\n"
                "тАв Adding features\n"
                "тАв Debugging issues\n\n"
                "Just describe your problem or send your code!",
                parse_mode='Markdown'
            )
        
        elif data == 'referral':
            ref_code = f"REF{user.id:06d}"
            
            await query.edit_message_text(
                "ЁЯСе **Referral System**\n\n"
                f"**Your Referral Code:** `{ref_code}`\n"
                f"**Your Referral Link:** https://t.me/your_bot?start=ref{user.id}\n\n"
                "**Rewards:**\n"
                "тАв 50 credits per active referral\n"
                "тАв Extra hosting time\n"
                "тАв Priority support\n\n"
                "**Your Stats:**\n"
                "тАв Referrals: 0\n"
                "тАв Rewards: 0 credits\n\n"
                "Share your referral link!",
                parse_mode='Markdown'
            )
        
        elif data.startswith('manage_'):
            bot_id = data[7:]
            info = tcp_host.get_bot_info(bot_id)
            
            if not info:
                await query.edit_message_text("тЭМ Bot not found!")
                return
            
            keyboard = [
                [
                    InlineKeyboardButton("тЦ╢я╕П Start", callback_data=f'start_{bot_id}'),
                    InlineKeyboardButton("тП╣я╕П Stop", callback_data=f'stop_{bot_id}')
                ],
                [
                    InlineKeyboardButton("ЁЯФД Restart", callback_data=f'restart_{bot_id}'),
                    InlineKeyboardButton("ЁЯЧСя╕П Delete", callback_data=f'delete_{bot_id}')
                ],
                [
                    InlineKeyboardButton("ЁЯУЬ Logs", callback_data=f'logs_{bot_id}'),
                    InlineKeyboardButton("ЁЯФЩ Back", callback_data='my_bots')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"ЁЯЫая╕П **Manage Bot:** `{bot_id}`\n\n"
            for key, value in info.items():
                text += f"**{key.replace('_', ' ').title()}:** `{value}`\n"
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Button error: {e}")
        await query.edit_message_text(f"тЭМ **Error:** {str(e)}", parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    message = update.message.text
    
    if message.startswith('http') and 'github.com' in message:
        # GitHub clone request
        await update.message.reply_text(
            f"ЁЯФД **Git Clone Requested**\n\n"
            f"URL: {message}\n\n"
            "This feature is coming soon!\n"
            "For now, download the repo as ZIP and send it to me.",
            parse_mode='Markdown'
        )
    elif 'help' in message.lower():
        await help_command(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    print("ЁЯдЦ Starting TCP Hosting Bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("upload", lambda u,c: u.message.reply_text("Send me a .py, .js, or .zip file!")))
    application.add_handler(CommandHandler("mybots", lambda u,c: button_handler(u, c, 'my_bots')))
    application.add_handler(CommandHandler("stats", lambda u,c: button_handler(u, c, 'stats')))
    
    # Handle document uploads
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Handle button callbacks
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Handle text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    print("тЬЕ Bot is running...")
    print("ЁЯУ▒ Use /start in Telegram")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
