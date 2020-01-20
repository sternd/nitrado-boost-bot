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

BOOST_TABLE_NAME = 'gameserver-boosts'
DB_REGION = 'us-west-2'

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

    def intialConnection(self):
        client = discord.Client()

        @client.event
        async def on_ready():
            print('Closing connection')
            await client.close()
            return None

        client.run(self.TOKEN)


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


class DBHelper:
    DB = None

    def __init__(self, db_type, db_region):
        self.DB = boto3.resource(db_type, region_name=db_region)

    def getDocument(self, table_name, key, val):
        table = self.DB.Table(table_name)
        item = table.get_item(Key={key: val})

        if not item:
            return None

        if 'Item' not in item:
            return None

        return item['Item']

    def createDocument(self, table_name, doc):
        table = self.DB.Table(table_name)
        response = table.put_item(Item=doc)

        return response

    def updateDocument(self, table_name, key_dict, update_expression, expression_attribute_values):
        table = self.DB.Table(table_name)
        response = table.update_item(Key=key_dict, UpdateExpression=update_expression, ExpressionAttributeValues=expression_attribute_values, ReturnValues="UPDATED_NEW")

        return response


# Handler for AWS Lambda to run the application
def handler(event, context):
    nitrado_helper = NitradoHelper()
    discord_helper = DiscordHelper()
    db_helper = DBHelper('dynamodb', 'us-west-2')

    if event == "initial-connection":
        discord_helper.intialConnection()
        return {
            'message': "Successfully initialized connection"
        }

    with open('nitrapi_account_config.json') as json_file:
        nitrapi_account_config = json.load(json_file)

    nitrapi_config = json.loads(nitrapi_account_config)

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
                "gameserver_id": gameserver_id,
                "boosts": parsed_boost_history
            })

    total_new_boosts = 0
    for gameserver_boost in boost_history_all_accounts:
        gameserver_id = gameserver_boost["gameserver_id"]
        gameserver_name = gameserver_boost["gameserver_name"]

        item = db_helper.getDocument(BOOST_TABLE_NAME, "gameserver_id", int(gameserver_id))

        if not gameserver_boost['boosts']:
            continue

        db_boosts = []

        if item and 'boosts' in item:
            db_boosts = json.loads(item['boosts'])

        new_gameserver_boosts = []
        for boost in gameserver_boost['boosts']:
            if not boostInList(boost, db_boosts):
                new_gameserver_boosts.append(boost)

        if not new_gameserver_boosts:
            continue

        new_db_boosts = []
        for boost in new_gameserver_boosts:
            embed = generateEmbed(gameserver_name, boost)
            dict_embed = embed.to_dict()

            response = discord_helper.createMessage(dict_embed)
            total_new_boosts += 1

            if not response:
                continue

            new_db_boosts.append(boost)

        if not new_db_boosts:
            continue

        if not item:
            doc = {
                "gameserver_id": int(gameserver_id),
                "boosts": json.dumps(new_db_boosts)
            }

            db_helper.createDocument('gameserver-boosts', doc)
        elif 'boosts' not in item or not item["boosts"]:
            db_helper.updateDocument(
                'gameserver-boosts',
                {"gameserver_id": int(gameserver_id)},
                "set boosts = :b",
                {":b": json.dumps(new_db_boosts)}
            )
        elif item["boosts"]:
            combined_db_boosts = db_boosts + new_db_boosts
            db_helper.updateDocument(
                'gameserver-boosts',
                {"gameserver_id": int(gameserver_id)},
                "set boosts = :b",
                {":b": json.dumps(combined_db_boosts)}
            )
        else:
            print("Unsure how to save boost data")

        if event == "slow-mode":
            print('Exiting for slow mode')
            return {
                'message': "Success in slow mode"
            }

    return {
        'message': "Success",
        'new_boosts': total_new_boosts
    }


def parseBoostHistory(boost_history):
    if boost_history is None:
        return None

    if boost_history['status'] != 'success':
        return None

    if not boost_history['data']:
        return None

    if not boost_history['data']['boosts']:
        return None

    return boost_history['data']['boosts']


def boostInList(boost, db_boosts):
    for db_boost in db_boosts:
        if boost['username'] == db_boost['username'] and boost['boosted_at'] == db_boost['boosted_at']:
            return True

    return False


def generateEmbed(gameserver_name, boost):
    booster = boost['username']
    boosted_at = datetime.strptime(boost['boosted_at'], "%Y-%m-%dT%H:%M:%S")

    boost_message = None

    if boost['message']:
        boost_message = boost['message']

    day_in_seconds = 86400
    days_boosted = round(boost['extended_for'] / day_in_seconds, 1)

    day_text = 'day'
    if days_boosted >= 2:
        day_text = 'days'

    embed = discord.Embed(title=f'{gameserver_name} BOOSTED!',
                          colour=discord.Colour(0x4a90e2),
                          description=f'{gameserver_name} has been boosted by **{booster}** for **{days_boosted} {day_text}**!\n\n')
    embed.set_footer(text="Boosted",
                     icon_url="https://cdn.discordapp.com/icons/626094990984216586/ceb7d3a814435bc9601276d07f44b9f3.png?size=128")

    if boost_message:
        embed.add_field(name='Boost Message', value=boost_message, inline=True)

    embed.__setattr__('timestamp', boosted_at)

    return embed


# FOR TESTING
#handler(None, None)
#handler('initial-connection', None)
#handler('slow-mode', None)
