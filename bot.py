# bot.py
import os

import discord
from dotenv import load_dotenv
import requests
from requests.exceptions import HTTPError, Timeout
import json
from datetime import datetime
import boto3

load_dotenv()

with open('nitrapi_account_config.json') as json_file:
    NITRAPI_ACCOUNT_CONFIG = json.load(json_file)


# Helper class to send Discord API requests
class DiscordHelper:
    TOKEN = os.getenv('DISCORD_TOKEN')
    BOT_CLIENT_ID = os.getenv('BOT_CLIENT_ID')
    CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
    DISCORD_BASE_URL = os.getenv('DISCORD_BASE_URL')
    DISCORD_MESSAGE_HISTORY = os.getenv('DISCORD_MESSAGE_HISTORY')
    DISCORD_CREATE_MESSAGE = os.getenv('DISCORD_CREATE_MESSAGE')
    DISCORD_EDIT_MESSAGE = os.getenv('DISCORD_EDIT_MESSAGE')

    def __init__(self):
        if self.TOKEN is None:
            raise Exception('Missing Discord Token')
        elif self.BOT_CLIENT_ID is None:
            raise Exception('Missing Bot Client ID')
        elif self.CHANNEL_ID is None:
            raise Exception('Missing Discord Channel ID')
        elif self.DISCORD_BASE_URL is None:
            raise Exception('Missing Discord Base URL')
        elif self.DISCORD_MESSAGE_HISTORY is None:
            raise Exception('Missing Discord Message History Path')
        elif self.DISCORD_CREATE_MESSAGE is None:
            raise Exception('Missing Discord Create Message Path')
        elif self.DISCORD_EDIT_MESSAGE is None:
            raise Exception('Missing Discord Edit Message Path')

    # Send a Discord API request
    def sendDiscordRequest(self, action, url, *params):
        # Do request here

        auth_token = f'Bot {self.TOKEN}'

        json_body = None

        if params is not None and params:
            json_body = params[0]

        try:
            if action == 'GET':
                response = requests.get(url, timeout=5, headers={"Authorization": auth_token})
            elif action == 'POST':
                response = requests.post(url, timeout=5, headers={"Authorization": auth_token}, json=json_body)
            elif action == 'PATCH':
                response = requests.patch(url, timeout=5, headers={"Authorization": auth_token}, json=json_body)
            else:
                raise Exception(f'Attempting to send request with unknown action: {action}')

            response.raise_for_status()
        except HTTPError as http_err:
            print(f'HTTP error occurred for {id}: {http_err}')
        except Timeout as timeout:
            print(f'HTTP timeout occurred for {id}: {timeout}')
        except Exception as err:
            print(f'Other error occurred for {id}: {err}')
        else:
            return response.json()

        return None

    # Get message ID of most recent message sent by bot
    def getLatestMessageID(self):
        # Make request for message history
        # Parse message ID
        url = self.DISCORD_BASE_URL + self.DISCORD_MESSAGE_HISTORY.replace(':channel_id', self.CHANNEL_ID, 1)

        response = self.sendDiscordRequest('GET', url)

        if response is None:
            return None

        for message in response:
            if message["author"]["id"] != self.BOT_CLIENT_ID:
                continue

            return message["id"]

        return None

    # Edit an existing Rich Embed message
    def editMessage(self, message_id, embed):
        # Make request to edit message
        url = self.DISCORD_BASE_URL + self.DISCORD_EDIT_MESSAGE.replace(':channel_id', self.CHANNEL_ID, 1).replace(
            ':message_id', message_id, 1)

        response = self.sendDiscordRequest('PATCH', url, {"embed": embed})

        if response is None:
            return None

        return response

    # Create a new Rich Embed message
    def createMessage(self, embed):
        # Make request to edit message
        url = self.DISCORD_BASE_URL + self.DISCORD_CREATE_MESSAGE.replace(':channel_id', self.CHANNEL_ID, 1)

        response = self.sendDiscordRequest('POST', url, {"embed": embed})

        if response is None:
            return None

        return response


class NitradoHelper:
    NITRAPI_BASE_URL = None
    NITRAPI_GAMESERVER_BOOST_HISTORY = None

    def __init__(self):

        self.NITRAPI_BASE_URL = os.getenv('NITRAPI_BASE_URL')
        self.NITRAPI_GAMESERVER_BOOST_HISTORY = os.getenv('NITRAPI_GAMESERVER_BOOST_HISTORY')

        if self.NITRAPI_BASE_URL is None:
            raise Exception('Missing NITRAPI_BASE_URL')
        if self.NITRAPI_GAMESERVER_BOOST_HISTORY is None:
            raise Exception('Missing NITRAPI_GAMESERVER_BOOST_HISTORY')

    def getBoostHistory(self, gameserver_id, token):
        url = self.NITRAPI_BASE_URL + self.NITRAPI_GAMESERVER_BOOST_HISTORY.replace(':id', gameserver_id, 1)
        auth_token = f'Bearer {token}'

        try:
            response = requests.get(url, timeout=3, headers={"Authorization": auth_token})
            response.raise_for_status()
        except HTTPError as http_err:
            print(f'HTTP error occurred for {id}: {http_err}')
        except Timeout as timeout:
            print(f'HTTP timeout occurred for {id}: {timeout}')
        except Exception as err:
            print(f'Other error occurred for {id}: {err}')
        else:
            return response.json()

        return None


# Handler for AWS Lambda to run the application
def handler(event, context):
    nitrado_helper = NitradoHelper()
    discord_helper = DiscordHelper()

    nitrapi_config = json.loads(NITRAPI_ACCOUNT_CONFIG)

    boost_history_all_accounts = []

    for account in nitrapi_config['nitrado_accounts']:
        auth_token = account["auth_token"]

        for gameserver in account["gameservers"]:
            if gameserver["enabled"] != True:
                continue

            gameserver_name = gameserver["gameserver_name"]
            gameserver_id = gameserver['gameserver_id']

            boost_history = nitrado_helper.getBoostHistory(gameserver_id, auth_token)
            parsed_boost_history = parseBoostHistory(boost_history)
            boost_history_all_accounts.append({
                "gameserver_name": gameserver_name,
                "boosts": parsed_boost_history
            })

    discord_helper = DiscordHelper()

    embed = discord.Embed(title="Valkyrie Boost History", colour=discord.Colour(0xf8e71c),
                          url="https://github.com/sternd/nitrado-boost-bot",
                          description="A listing of all boosts made by our wonderful players for the Valkyrie Ark servers. The posting will be updated every hour.")
    embed.set_thumbnail(
        url="https://cdn.discordapp.com/icons/626094990984216586/ceb7d3a814435bc9601276d07f44b9f3.png?size=128")
    embed.set_footer(text="Updated",
                     icon_url="https://cdn.discordapp.com/icons/626094990984216586/ceb7d3a814435bc9601276d07f44b9f3.png?size=128")

    embed = addGameserverBoostHistoryToEmbed(embed, boost_history_all_accounts)

    embed.__setattr__('timestamp', datetime.utcnow())
    embed.__setattr__('colour', discord.Color('0x4A90E2'))

    dict_embed = embed.to_dict()

    message_id = discord_helper.getLatestMessageID()

    if message_id is None:
        discord_helper.createMessage(dict_embed)
    else:
        discord_helper.editMessage(message_id, dict_embed)

    return {
        'message': "Success"
    }


def parseBoostHistory(boost_history):
    if boost_history is None:
        return None

    if boost_history['status'] != 'success':
        return None

    if not boost_history['boosts']:
        return None

    return boost_history['boosts']


def addGameserverBoostHistoryToEmbed(embed, boost_history_all_accounts):
    for gameserver_boost in boost_history_all_accounts:
        formatted_message = ""

        for boost in gameserver_boost:
            formatted_datetime = datetime.strptime(boost['boosted_at'], '%Y-%m-%dT%H:%M:%S')
            date = formatted_datetime.date()

            day_in_seconds = 86400
            days_boosted = round(boost['extended_for'] / day_in_seconds, 1)

            day_text = 'day'
            if days_boosted >= 2:
                day_text = 'days'

            formatted_message += '**' + boost['username'] + '**\n' + f'Date: {date}\n' + f'Boost: {days_boosted} {day_text}\n\n'

        embed.add_field(name='__**' + gameserver_boost['gameserver_name'] + '**__', value=formatted_message,
                        inline=False)

    return embed




# FOR TESTING
# handler(None, None)
