import datetime
import time
from typing import List
import requests
import pytz
import eospy.cleos
import eospy.keys
import urllib3
from colorama import Fore, Back, Style, init
from account import Account
import json
import traceback
import threading
from multiprocessing.pool import ThreadPool

init(autoreset=True)

accounts = [
            # Your accounts
            ]

servers = ['https://wax.pink.gg', 'https://wax.cryptolions.io', 'https://wax.eosphere.io',
           'https://api.wax.alohaeos.com', 'https://api.waxsweden.org', 'https://wax.dapplica.io',
           'https://api.wax.greeneosio.com', 'https://wax.eu.eosamsterdam.net', 'https://api.wax.bountyblok.io']
current_server = servers[1]
ce = eospy.cleos.Cleos(url=current_server)
will_exchange_milk = 1
is_stoped = False
cancel_withdrawal = False

def log_add(text, color):
    print(f'{datetime.datetime.utcnow()}: {color}{text}')

def reconnect_cleos():
    global ce, current_server, servers
    i = 0
    for server in servers:
        i += 1
        if current_server == server:
            if i >= len(servers):
                i = 0
            current_server = servers[i]
            break
    ce = eospy.cleos.Cleos(url=current_server)

    for account in accounts:
        account.key = eospy.keys.EOSKey(account.private_keys[1])

    log_add(f'Recconected to {current_server}', Fore.LIGHTMAGENTA_EX)

def find_account(account_name):
    account = [acc for acc in accounts if acc.account_name == account_name]
    if len(account) > 0:
        return account[0]
    else:
        return None

def find_balance(balances, balance_id):
    for balance in balances:
        if balance.split()[1] == balance_id:
            return float(balance.split()[0])
    return 0

def check_max_claims(item, max_claims):
    if len(item['day_claims_at']) < max_claims:
        return True
    else:
        first_time = datetime.datetime.utcfromtimestamp(int(item['day_claims_at'][0]))
        if datetime.datetime.utcnow() > first_time + datetime.timedelta(days=1):
            return True
        else:
            return False

def parse_assets(account_name):
    response = requests.get('https://wax.api.atomicassets.io/atomicassets/v1/assets?'
                            'page=1&limit=1000&template_blacklist=260676&'
                            f'collection_name=farmersworld&owner={account_name}')
    js = json.loads(response.text)
    return js['data']

def check_assets_amount(items, template_id):
    count = 0
    for item in items:
        if int(item['template_id']) == template_id:
            count += 1
    return count

def find_asset_ids(account, template_id, count=1):
    asset_ids = []
    assets = parse_assets(account.account_name)
    asset = [i for i in assets if int(i['template']['template_id']) == template_id]
    if len(asset) < 1:
        log_add(f"[{account.account_name}] Couldn't find asset with template id = {template_id}", Fore.RED)
        return None
    for i in range(count):
        if len(asset) > i:
            asset_ids.append(asset[i]['asset_id'])
        else:
            break
    return asset_ids

def check_items_list(items : List[str]):
    breeding_items = [i for i in items if i['type'] == 'breedings']
    for breeding_item in breeding_items:
        cow_items = [i for i in items if i['type'] == 'animals' and i['asset_id'] == breeding_item['bearer_id']]
        if len(cow_items) > 0:
            items.remove(cow_items[0])
        cow_items = [i for i in items if i['type'] == 'animals' and i['asset_id'] == breeding_item['partner_id']]
        if len(cow_items) > 0:
            items.remove(cow_items[0])

def build_transaction(account, contract, action_name, data):
    payload = {
        "account": contract,
        "name": action_name,
        "authorization": [{
            "actor": account,
            "permission": "active",
        }],
    }

    data = ce.abi_json_to_bin(payload['account'], payload['name'], data)
    # Inserting payload binary form as "data" field in original payload
    payload['data'] = data['binargs']
    # final transaction formed
    trx = {"actions": [payload]}
    trx['expiration'] = str(
        (datetime.datetime.utcnow() + datetime.timedelta(seconds=60)).replace(tzinfo=pytz.UTC))

    return trx

def push_transaction(trx, key):
    try:
        resp = ce.push_transaction(trx, key, broadcast=True)
    except:
        log_add(traceback.format_exc(), Fore.LIGHTRED_EX)
        #reconnect_cleos()
        #time.sleep(20)
        #return push_transaction(trx, key)
        return False

    if resp['processed']['receipt']['status'] == 'executed':
        return True
    else:
        return False

def parse_configs():
    try:
        configs = []

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='toolconfs',
                              upper_bound=None)
        configs.extend(result['rows'])

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='anmconf',
                              upper_bound=None)
        configs.extend(result['rows'])

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='cropconf',
                              upper_bound=None)
        configs.extend(result['rows'])

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='breedconf',
                              upper_bound=None)
        configs.extend(result['rows'])

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='bldconf',
                              upper_bound=None)
        configs.extend(result['rows'])

        result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                              lower_bound=None, scope='farmersworld', table='mbsconf',
                              upper_bound=None)
        configs.extend(result['rows'])

        return configs
    except:
        log_add(f'Failed to parse configs', Fore.LIGHTRED_EX)
        return parse_configs()

def parse_market_config():
    result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                          lower_bound=None, scope='farmersworld', table='mktconf',
                          upper_bound=None)
    return result['rows']

def parse_game_config():
    result = ce.get_table(code='farmersworld', index_position=1, key_type='', limit=100,
                          lower_bound=None, scope='farmersworld', table='config',
                          upper_bound=None)
    return result['rows'][0]

def find_config(template_id, item_type):
    config = [c for c in configs if c['template_id'] == template_id]
    if len(config) == 1:
        return config[0]
    elif len(config) > 1:
        if item_type == 'animals':
            return config[0]
        elif item_type == 'breedings':
            return config[1]
        else:
            return None
    else:
        return None

def find_by_template_id(items_list, template_id):
    for item in items_list:
        if item['template_id'] == template_id:
            return item
    return None

def parse_account_info(account_name):
    result = ce.get_table(code='farmersworld', index_position=1, key_type='i64', limit=100,
                          lower_bound=account_name, scope='farmersworld', table='accounts',
                          upper_bound=account_name)
    return result['rows'][0]

def check_gold_balance(account_name, need_gold):
    account_info = parse_account_info(account_name)
    if find_balance(account_info['balances'], 'GOLD') >= need_gold:
        return True
    else:
        return False

def check_food_balance(account_name, need_food):
    account_info = parse_account_info(account_name)
    if find_balance(account_info['balances'], 'FOOD') >= need_food:
        return True
    else:
        return False

def check_energy(account_name, need_energy):
    account_info = parse_account_info(account_name)
    if account_info['energy'] >= need_energy:
        return True, None
    else:
        return False, account_info['max_energy'] - account_info['energy']

def recover(account, energy_recovered):
    if not check_food_balance(account.account_name, energy_recovered/5):
        log_add(f'[{account.account_name}] NOT ENOUGH {Fore.LIGHTRED_EX}FOOD', Fore.RED)
        return

    data = {'owner':account.account_name, 'energy_recovered':energy_recovered}
    trx = build_transaction(account.account_name, 'farmersworld', 'recover', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Recovering for {energy_recovered} has been done successfully', Fore.GREEN)
    else:
        log_add(f'[{account.account_name}] Recovering for {energy_recovered} failed', Fore.RED)

def buy(account, template_id, quantity):
    configs = parse_market_config()
    config = find_by_template_id(configs, template_id)
    if config is not None:
        price = float(config['cost'][0].split()[0])
        if not check_gold_balance(account.account_name, price):
            log_add(f'[{account.account_name}] Not enough {Fore.YELLOW}GOLD {Fore.RED} for buying', Fore.RED)
            return False
    else:
        log_add(f"Couldn't find market config", Fore.RED)
        return False

    data = {'owner': account.account_name, 'template_id': template_id, 'zz': quantity}
    trx = build_transaction(account.account_name, 'farmersworld', 'mktbuy', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Buying {template_id} has been done successfully', Fore.GREEN)
        return True
    else:
        log_add(f'[{account.account_name}] Buying {template_id} failed', Fore.RED)
        return False

def claim(account, asset_id):
    data = {'owner': account.account_name, 'asset_id': asset_id}
    trx = build_transaction(account.account_name, 'farmersworld', 'claim', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Claiming for {asset_id} has been done successfully', Fore.GREEN)
    else:
        log_add(f'[{account.account_name}] Claiming for {asset_id} failed', Fore.RED)

def crop_claim(account, crop_id):
    data = {'owner': account.account_name, 'crop_id': crop_id}
    trx = build_transaction(account.account_name, 'farmersworld', 'cropclaim', data)

    if push_transaction(trx, account.key):
        return True
    else:
        log_add(f'[{account.account_name}] Claiming for crop {crop_id} failed', Fore.RED)
        return False

def membership_claim(account, asset_id):
    data = {'asset_id': asset_id, 'owner': account.account_name}
    trx = build_transaction(account.account_name, 'farmersworld', 'mbsclaim', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully claimed for membership {asset_id}', Fore.GREEN)
        return True
    else:
        log_add(f'[{account.account_name}] Claiming for membership {asset_id} failed', Fore.RED)
        return False

def feed(account, to, consumable_asset_ids, cow_asset_id):
    memo = f'feed_animal:{cow_asset_id}'
    data = {'from': account.account_name, 'to': to, 'asset_ids': consumable_asset_ids, 'memo': memo}
    trx = build_transaction(account.account_name, 'atomicassets', 'transfer', data)

    if push_transaction(trx, account.key):
        return True
    else:
        log_add(f'[{account.account_name}] Feeding failed', Fore.RED)
        return False

def breed(account, to, consumable_asset_ids, cow_asset_ids):
    memo = f'breed_animal:{cow_asset_ids}'
    data = {'from': account.account_name, 'to': to, 'asset_ids': consumable_asset_ids, 'memo': memo}
    trx = build_transaction(account.account_name, 'atomicassets', 'transfer', data)

    if push_transaction(trx, account.key):
        return True
    else:
        log_add(f'[{account.account_name}] Breeding failed', Fore.RED)
        return False

def build(account, asset_id):
    data = {'owner': account.account_name, 'asset_id': asset_id}
    trx = build_transaction(account.account_name, 'farmersworld', 'bldclaim', data)

    if push_transaction(trx, account.key):
        return True
    else:
        log_add(f'[{account.account_name}] Building for {asset_id} failed', Fore.RED)
        return False

def wear_crop(account, assets_ids):
    data = {'from': account.account_name, 'to': 'farmersworld', 'asset_ids': assets_ids, 'memo': 'stake'}
    trx = build_transaction(account.account_name, 'atomicassets', 'transfer', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully worn a crop', Fore.LIGHTGREEN_EX)
        return True
    else:
        log_add(f'[{account.account_name}] Wearing a crop failed', Fore.RED)
        return False

def exchange_milk(account):
    assets_ids = find_asset_ids(account, 298593, 1000)

    data = {'from': account.account_name, 'to': 'farmersworld', 'asset_ids': assets_ids, 'memo': 'burn'}
    trx = build_transaction(account.account_name, 'atomicassets', 'transfer', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully exchanged {len(assets_ids)} milk', Fore.GREEN)
        return True
    else:
        log_add(f'[{account.account_name}] Exchanging {len(assets_ids)} milk failed', Fore.RED)
        return False

def repair(account, asset_id, full_durability):
    if not check_gold_balance(account.account_name, full_durability/5):
        log_add(f'[{account.account_name}] NOT ENOUGH {Fore.YELLOW}GOLD', Fore.RED)
        return False

    data = {'asset_owner':account.account_name, 'asset_id':asset_id}
    trx = build_transaction(account.account_name, 'farmersworld', 'repair', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Repairing for {asset_id} has been done successfully', Fore.GREEN)
        return True
    else:
        log_add(f'[{account.account_name}] Repairing for {asset_id} failed', Fore.RED)
        return False

def withdraw(account, quantities, fee):
    data = {'owner': account.account_name, 'quantities': [quantities], 'fee': fee}
    trx = build_transaction(account.account_name, 'farmersworld', 'withdraw', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully has withdrawn {quantities} with {fee}% fee', Fore.LIGHTMAGENTA_EX)
        return True
    else:
        log_add(f'[{account.account_name}] Withdrawal of {quantities} with {fee}% fee was failed', Fore.RED)
        return False

def deposit(account, quantities):
    data = {'from': account.account_name, 'to': 'farmersworld', 'quantities': [quantities], 'memo': 'deposit'}
    trx = build_transaction(account.account_name, 'farmerstoken', 'transfers', data)

    if push_transaction(trx, account.key):
        log_add(f'[{account.account_name}] Successfully has deposited {quantities}', Fore.LIGHTMAGENTA_EX)
        return True
    else:
        log_add(f'[{account.account_name}] Failed to deposit {quantities}', Fore.RED)
        return False

def try_withdraw(account, amount, max_fee):
    global cancel_withdrawal
    log_add(f'Waiting for needed {max_fee}% fee or less', Fore.LIGHTYELLOW_EX)
    config = parse_game_config()
    while int(config['fee']) > max_fee and not cancel_withdrawal:
        estimated_time = datetime.datetime.utcfromtimestamp(int(config['last_fee_updated']))
        while datetime.datetime.utcnow() < estimated_time + datetime.timedelta(hours=1) and not cancel_withdrawal:
            time.sleep(30)
        if cancel_withdrawal:
            break
        time.sleep(60)
        config = parse_game_config()
    if not cancel_withdrawal:
        log_add(f'Try to withdraw {amount} with {config["fee"]}% fee', Fore.WHITE)
        withdraw(account, amount, int(config['fee']))
    else:
        log_add('Withdrawal canceled', Fore.LIGHTMAGENTA_EX)
        cancel_withdrawal = False

def parse_items(account):
    try:
        account.items = []

        for table in account.tables:
            result = ce.get_table(code='farmersworld', index_position=table[1], key_type='i64', limit=100,
                                  lower_bound=account.account_name, scope='farmersworld', table=table[0],
                                  upper_bound=account.account_name)
            for row in result['rows']:
                row['type'] = table[0]

            account.items.extend(result['rows'])

        check_items_list(account.items)
    except:
        parse_items(account)
        log_add('Error while parsing items', Fore.LIGHTRED_EX)

def check_items(account):
    is_changed = False

    for item in account.items:
        config = find_config(item['template_id'], item['type'])
        if config is None:
            log_add(f"[{account.account_name}] Couldn't find config", Fore.RED)
            return

        if item['type'] == 'tools':
            estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
            if datetime.datetime.utcnow() >= estimated_time:
                is_changed = True

                if item['current_durability'] <= config['durability_consumed']:
                    if repair(account, item['asset_id'], item['durability']) is False:
                        continue
                is_enough_energy, need_energy = check_energy(account.account_name, config['energy_consumed'])
                if not is_enough_energy:
                    recover(account, need_energy)
                    # 500 - MAX ENERGY, DON'T UPDATE ONLINE

                claim(account, item['asset_id'])
        elif item['type'] == 'crops':
            estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
            if datetime.datetime.utcnow() >= estimated_time:
                is_changed = True

                is_enough_energy, need_energy = check_energy(account.account_name, 200+config['energy_consumed'])
                if not is_enough_energy:
                    recover(account, need_energy)
                    # 500 - MAX ENERGY, DON'T UPDATE ONLINE

                if crop_claim(account, item['asset_id']):
                    log_add(f'[{account.account_name}] Claiming for crop {item["asset_id"]} has been done successfully '
                            f'{item["times_claimed"] + 1}/{config["required_claims"]}', Fore.GREEN)
                    if item["times_claimed"] + 1 >= config["required_claims"]:
                        while True:
                            try:
                                if item['template_id'] == 298595:
                                    barleys = find_asset_ids(account, 298595, 1)
                                    if barleys is None: barleys = []

                                    if len(barleys) > 0:
                                        wear_crop(account, barleys)
                                    else:
                                        if buy(account, 298595, 1):
                                            time.sleep(15)
                                            barleys = find_asset_ids(account, 298595, 1)
                                            wear_crop(account, barleys)
                                elif item['template_id'] == 298596:
                                    corns = find_asset_ids(account, 298596, 1)
                                    if corns is None: corns = []

                                    if len(corns) > 0:
                                        wear_crop(account, corns)
                                    else:
                                        if buy(account, 298596, 1):
                                            time.sleep(15)
                                            corns = find_asset_ids(account, 298596, 1)
                                            wear_crop(account, corns)
                                time.sleep(15)
                                break
                            except:
                                log_add(f'[{account.account_name}] Cannot buy and wear a crop', Fore.LIGHTRED_EX)
                                time.sleep(15)
                                continue
        elif item['type'] == 'animals':
            estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
            if datetime.datetime.utcnow() >= estimated_time:
                if check_max_claims(item, config['daily_claim_limit']):
                    is_changed = True
                    consumable_asset_id = find_asset_ids(account, config['consumed_card'])
                    if consumable_asset_id is not None and len(consumable_asset_id) > 0:
                        is_enough_energy, need_energy = check_energy(account.account_name, 200)
                        if not is_enough_energy:
                            recover(account, need_energy)
                        if feed(account, 'farmersworld', [consumable_asset_id[0]], item['asset_id']):
                            log_add(f'[{account.account_name}] Feeding has been done successfully '
                                    f'{item["times_claimed"] + 1}/{config["required_claims"]}', Fore.LIGHTGREEN_EX)
                            if item["times_claimed"] + 1 >=config["required_claims"] and will_exchange_milk:
                                time.sleep(20)
                                exchange_milk(account)
                            else: time.sleep(10)
        elif item['type'] == 'breedings':
            estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
            if datetime.datetime.utcnow() >= estimated_time:
                if check_max_claims(item, config['daily_claim_limit']):
                    is_changed = True
                    consumable_asset_id = find_asset_ids(account, config['consumed_card'])
                    if consumable_asset_id is not None and len(consumable_asset_id) > 0:
                        if breed(account, 'farmersworld', [consumable_asset_id[0]], f'{item["bearer_id"]},{item["partner_id"]}'):
                            log_add(f'[{account.account_name}] Breeding has been done successfully '
                                    f'{item["times_claimed"] + 1}/{config["required_claims"]}', Fore.LIGHTGREEN_EX)
        elif item['type'] == 'buildings':
            if item['times_claimed'] < config['required_claims']:
                estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
                if datetime.datetime.utcnow() >= estimated_time:
                    is_changed = True
                    is_enough_energy, need_energy = check_energy(account.account_name, config['energy_consumed'])
                    if not is_enough_energy:
                        recover(account, need_energy)
                    if build(account, item['asset_id']):
                        log_add(f'[{account.account_name}] Building for {item["asset_id"]} has been done successfully '
                                f'{item["times_claimed"]+1}/{config["required_claims"]}', Fore.LIGHTGREEN_EX)
                        if item["times_claimed"]+1 >= config["required_claims"]:
                            if config['template_id'] == '298592':
                                barleys = find_asset_ids(account, 298595, 5)
                                if barleys is None: barleys = []

                                if len(barleys) > 0:
                                    wear_crop(account, barleys)
                                else:
                                    if buy(account, 298595, 5):
                                        time.sleep(15)
                                        barleys = find_asset_ids(account, 298595, 5)
                                        wear_crop(account, barleys)

                            corns = find_asset_ids(account, 298596, 3)
                            if corns is None: corns = []

                            if len(corns) > 0:
                                wear_crop(account, corns)
                            else:
                                if buy(account, 298596, 3):
                                    time.sleep(15)
                                    corns = find_asset_ids(account, 298596, 3)
                                    wear_crop(account, corns)
        elif item['type'] == 'mbs':
            estimated_time = datetime.datetime.utcfromtimestamp(int(item['next_availability']))
            if datetime.datetime.utcnow() >= estimated_time:
                is_changed = True

                is_enough_energy, need_energy = check_energy(account.account_name, 100)
                if not is_enough_energy:
                    recover(account, need_energy)

                membership_claim(account, item['asset_id'])

    if is_changed:
        time.sleep(15)
        parse_items(account)

def update_data():
    try:
        global configs
        configs = parse_configs()
        for account in accounts:
            account.key = eospy.keys.EOSKey(account.private_keys[1])
            parse_items(account)
    except:
        return update_data()
    log_add('Successfully updated', Fore.YELLOW)

def monitoring():
    while not is_stoped:
        for account in accounts:
            try:
                check_items(account)
            except:
                log_add(f'[{account.account_name}] HANDLED ERROR: {traceback.format_exc()}', Fore.RED)
                parse_items(account)
            time.sleep(10)
    log_add('STOPPED', Fore.YELLOW)

print('Commands:\n'
      '/update - will update all accounts information\n'
      '/wear {account_name} {asset_id} - stake asset into game\n'
      '/exchange_milk {int} - turn on/off (1/0) exchanging milk\n'
      '/stop - to stop program\n'
      '/run - to start program\n'
      '/deposit {account_name} {x.0000 FWG/FWW/FWF} - to deposit some quantities to game\n'
      '/withdraw {account_name} {x.0000 GOLD/WOOD/FOOD} {max_fee} - to withdraw some quantities from game '
      'with expected fee\n'
      '/cancel withdrawal - to cancel withdrawal\n'
      '/list_accounts - to get list of accounts\n')

global configs

update_data()
threading.Thread(target=monitoring).start()

log_add('STARTED', Fore.YELLOW)

while True:
    command = input()
    if '/update' in command:
        update_data()
    elif '/wear' in command:
        data = command.split()
        account = find_account(data[1])
        if account is None:
            log_add(f"Couldn't find an account {data[2]}")
            continue
        wear_crop(account, data[2:])
    elif '/exchange_milk' in command:
        data = command.split()
        exchange_milk = int(data[1])
        print(f'exchange_milk changed to {exchange_milk}')
    elif '/stop' in command:
        is_stoped = True
        log_add('STOPPING..', Fore.MAGENTA)
    elif '/run' in command:
        is_stoped = False
        update_data()
        threading.Thread(target=monitoring).start()
        log_add('STARTED', Fore.LIGHTYELLOW_EX)
    elif '/deposit' in command:
        data = command.split()
        account = find_account(data[1])
        if account is not None:
            deposit(account, f'{data[2]} {data[3]}')
        else:
            log_add(f'Account with {data[1]} account_name was not found', Fore.LIGHTRED_EX)
    elif '/withdraw' in command:
        data = command.split()
        account = find_account(data[1])
        if account is not None:
            threading.Thread(target=try_withdraw, args=[account, f'{data[2]} {data[3]}', int(data[4])]).start()
        else:
            log_add(f'Account with {data[1]} account_name was not found', Fore.LIGHTRED_EX)
    elif '/cancel' in command:
        data = command.split()
        if data[1] == 'withdrawal':
            cancel_withdrawal = True
            log_add('Start cancelling withdrawal..', Fore.LIGHTYELLOW_EX)
        else:
            log_add(f"Couldn't find such a method, expected:\nwithdrawal", Fore.LIGHTRED_EX)
    elif '/list_accounts' in command:
        for account in accounts:
            print(account.account_name)
        log_add(f'Accounts were listed', Fore.LIGHTYELLOW_EX)
