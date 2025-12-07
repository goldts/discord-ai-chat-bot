import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import aiohttp
import asyncio
import logging


try:
    import google.generativeai as genai
    HAS_GOOGLE = True
except Exception:
    genai = None
    HAS_GOOGLE = False


load_dotenv()


DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')


if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in .env file")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")


intents = discord.Intents.default()
intents.message_content = True  
intents.guilds = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!', '?'), intents=intents)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


BOT_ACTIVE = True

ALLOWED_STARTER_ID = 1259621508041539645


if HAS_GOOGLE and GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        logger.info('Google Generative AI configured')
    except Exception as e:
        logger.warning('Failed to configure Google Generative AI: %s', e)

@bot.event
async def on_ready():
    """Called when bot successfully connects to Discord"""
    print(f"✅ Bot logged in as {bot.user}")
    print(f"📡 Bot is ready to respond to mentions")



@bot.command(name='ping')
async def ping(ctx):
    """Reply with pong + latency for quick testing."""
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f'Pong! {latency_ms}ms')


class MoodView(discord.ui.View):
    def __init__(self, *, timeout: float | None = 60):
        super().__init__(timeout=timeout)

    async def _handle_and_delete(self, interaction: discord.Interaction, label: str):

        responded = False
        try:
            await interaction.response.send_message(f'You clicked: {label}', ephemeral=True)
            responded = True
        except Exception as e:
            
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(f'You clicked: {label}', ephemeral=True)
                responded = True
            except Exception as e2:
               
                print(f"Failed to acknowledge interaction: {e} / {e2}")

        
        if not responded:
            try:
                await interaction.followup.send(f'You clicked: {label}', ephemeral=True)
            except Exception:
               
                pass

       
        await asyncio.sleep(3)
        try:
            if interaction.message:
                await interaction.message.delete()
        except Exception as e:
            print(f"Failed to delete interaction message: {e}")

    @discord.ui.button(label='Bad', style=discord.ButtonStyle.danger)
    async def bad(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self._handle_and_delete(interaction, 'Bad')

    @discord.ui.button(label='Ok', style=discord.ButtonStyle.secondary)
    async def ok(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self._handle_and_delete(interaction, 'Ok')

    @discord.ui.button(label='Good', style=discord.ButtonStyle.success)
    async def good(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self._handle_and_delete(interaction, 'Good')


@bot.command(name='test')
async def test_cmd(ctx):
    """Send an embed with three mood buttons that deletes after click."""
    embed = discord.Embed(title='Rate The bot', description='Bad, Ok, or Good?', color=discord.Color.green())
    view = MoodView()
    await ctx.send(embed=embed, view=view)


@bot.command(name='stop')
async def stop_cmd(ctx):
    """Pause the bot so it ignores commands/mentions until restarted with ?start."""
    global BOT_ACTIVE
   
    try:
        app = await bot.application_info()
        is_owner = ctx.author.id == app.owner.id
    except Exception:
        is_owner = False

    if not is_owner and not getattr(ctx.author, 'guild_permissions', None) or (hasattr(ctx.author, 'guild_permissions') and not ctx.author.guild_permissions.administrator):
        await ctx.send("You don't have permission to stop the bot. (Owner or server admin required)")
        return

    BOT_ACTIVE = False
    await ctx.send('Bot paused. Use ?start to resume.')


@bot.command(name='start')
async def start_cmd(ctx):
    """Resume bot operation after a pause."""
    global BOT_ACTIVE
    try:
        app = await bot.application_info()
        is_owner = ctx.author.id == app.owner.id
    except Exception:
        is_owner = False

    if not is_owner and not getattr(ctx.author, 'guild_permissions', None) or (hasattr(ctx.author, 'guild_permissions') and not ctx.author.guild_permissions.administrator):
        await ctx.send("You don't have permission to start the bot. (Owner or server admin required)")
        return

    BOT_ACTIVE = True
    await ctx.send('Bot resumed. Ready to respond.')

@bot.event
async def on_message(message):
    """
    Called when a message is sent in any channel the bot can see.
    Responds to mentions with AI-generated responses.
    """
    
   
    try:
        logger.info("Incoming message from %s in %s: %s", message.author, getattr(message.channel, 'name', message.channel), (message.content[:200] if message.content else '<no content>'))
    except Exception:
       
        pass

 
    if message.author.bot:
        return


    if not BOT_ACTIVE:
        content = message.content.strip()
        if content.startswith('?start') or content.startswith('!start'):
            await bot.process_commands(message)
        return
   
    if bot.user not in message.mentions:
       
        await bot.process_commands(message)
        return
    
   
    async with message.channel.typing():
        try:
            
            prompt = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
            
            if not prompt:
                prompt = "Hello! Say something nice."
            
           
            response = await get_ai_response(prompt)
            

            if len(response) > 2000:
                for chunk in [response[i:i+1990] for i in range(0, len(response), 1990)]:
                    await message.reply(chunk)
            else:
                await message.reply(response)
                
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            await message.reply("Sorry, I encountered an error while processing your request.")

  
    await bot.process_commands(message)

async def get_ai_response_openai(prompt: str) -> tuple[str, int]:
    """
    Get AI response from OpenAI API.
    
    Args:
        prompt: User's message/prompt
        
    Returns:
        AI-generated response text
    """
    url = "https://api.openai.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful Discord bot assistant. Keep responses concise and friendly. Respond in a natural conversational way."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    
   
    max_retries = 2
    backoff = 1.0

    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as response:
                   
                    try:
                        body = await response.text()
                    except Exception as read_err:
                        body = f"<failed to read body: {read_err}>"

                    if response.status == 200:
                        try:
                            data = await response.json()
                            return data['choices'][0]['message']['content'].strip(), 200
                        except Exception as e:
                            print(f"Failed to parse OpenAI JSON response: {e}")
                            print('Response body:', body)
                            return "AI returned an unexpected response format. Try again later."

                   
                    print(f"OpenAI API error (status={response.status})")
                    print('Response body:', body)

                
                    if response.status == 401:
                        return (
                            "AI authentication failed (invalid API key)."
                            " The bot owner should check the OPENAI_API_KEY environment variable.",
                            401,
                        )
                    if response.status == 429:
                       
                        if attempt < max_retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        return "I'm being rate-limited by the AI service. Try again in a moment.", 429
                    if 500 <= response.status < 600:
                  
                        if attempt < max_retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        return "AI service is currently unavailable. Try again later.", response.status

                    return "I'm having trouble connecting to my AI brain right now. Try again in a moment!", response.status

        except asyncio.TimeoutError:
            print(f"Timeout contacting OpenAI (attempt {attempt+1})")
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            return "The request timed out. Please try again!", 504
        except aiohttp.ClientConnectorError as e:
            print(f"Network/connection error contacting OpenAI: {e}")
            return "Network error contacting AI service. Please check the host machine's internet connection.", 503
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return f"An error occurred: {str(e)}", 500
    return "Unexpected error contacting AI service.", 520


async def get_ai_response_ollama(prompt: str) -> tuple[str, int]:
    """Try a local Ollama instance as a fallback. Returns (text, status).

    Ollama must be running locally (http://localhost:11434).
    """
    ollama_url = 'http://localhost:11434/api/generate'
    payload = {
        'model': os.getenv('OLLAMA_MODEL', 'mistral'),
        'prompt': prompt,
        'stream': False,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ollama_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                text = await resp.text()
                if resp.status == 200:
                   
                    try:
                        data = await resp.json()
                      
                        return data.get('response') or data.get('text') or text, 200
                    except Exception:
                        return text, 200
                else:
                    print(f"Ollama error (status={resp.status}): {text}")
                    return f"Ollama fallback failed (status={resp.status})", resp.status
    except Exception as e:
        print(f"Error contacting Ollama: {e}")
        return f"Error contacting local Ollama: {e}", 503


async def get_ai_response(prompt: str) -> str:
    """Primary API caller with fallback to local Ollama when OpenAI quota is exceeded."""
   
    if GOOGLE_API_KEY and HAS_GOOGLE:
        try:
            g = await get_ai_response_google(prompt)
            return g
        except Exception as e:
            print(f"Google Generative AI call failed: {e}")

    openai_result, status = await get_ai_response_openai(prompt)

    if status == 200:
        return openai_result

    
    if status in (429, 401) or (500 <= status < 600):
      
        use_ollama = os.getenv('USE_OLLAMA', 'false').lower() in ('1', 'true', 'yes')
        if use_ollama:
            print('Attempting Ollama fallback...')
            ollama_text, ollama_status = await get_ai_response_ollama(prompt)
            if ollama_status == 200:
                return ollama_text
            else:
               
                return ollama_text

   
    return openai_result


async def get_ai_response_google(prompt: str) -> str:
    """Call Google Generative AI (gemini) via the google-generativeai client.

    This code uses the genai client which is configured at startup when
    GOOGLE_API_KEY is present in the environment.
    """
    if not HAS_GOOGLE:
        raise RuntimeError('google-generativeai package not installed')
    if not GOOGLE_API_KEY:
        raise RuntimeError('GOOGLE_API_KEY not configured')

    
    def call_sync():
        
        model = os.getenv('GOOGLE_MODEL', 'gemini-pro')
        model_obj = genai.get_model(model)
        resp = model_obj.generate_message({'content': prompt})
       
        if hasattr(resp, 'text'):
            return resp.text
        try:
            return resp.output[0].content[0].text
        except Exception:
            return str(resp)

    return await asyncio.to_thread(call_sync)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
