import random
import time

import redis

from bitz.helper import BitZHelper
from constants import Constants
from utils import build_bit_z_sign, http_post, extract_symbol


class BitZTrade(object):
    ORDER_RESOURCE = '/api_v1/tradeAdd'
    CANCEL_RESOURCE = '/api_v1/tradeCancel'
    OPEN_ORDERS_RESOURCE = '/api_v1/openOrders'

    def __init__(self, url, api_key, secret_key, trade_pwd):
        # type: (str, str, str, str) -> None
        self.__url = url
        self.__api_key = api_key
        self.__secret_key = secret_key
        self.__trade_pwd = trade_pwd
        self.__redis = redis.StrictRedis()

    def get_position(self, coin: str) -> float:
        """

        :param coin:
        :return: corresponding position
        """
        quantity = self.__redis.hget(Constants.REDIS_KEY_BIT_Z_POSITIONS, coin)
        if quantity is None:
            quantity = 0.0
        else:
            quantity = float(quantity.decode())
        return quantity

    def update_position(self, coin: str, delta: float):
        quantity = self.get_position(coin)
        self.__redis.hset(Constants.REDIS_KEY_BIT_Z_POSITIONS, coin, quantity + delta)

    def order(self, order_type, coin, price, number):
        # type: (str, str, str, str) -> str
        params = {'api_key': self.__api_key, 'timestamp': str(int(time.time())),
                  'nonce': '%06d' % random.randint(0, 999999), 'coin': coin, 'type': order_type, 'price': price,
                  'number': number, 'tradepwd': self.__trade_pwd}
        params['sign'] = build_bit_z_sign(params, self.__secret_key)
        # {'code': 0, 'msg': 'Success', 'data': {'id': '85995372'}}
        result = http_post(self.__url + BitZTrade.ORDER_RESOURCE, params)
        # print(result)
        if result['code'] == 0:
            order_id = result['data']['id']
            self.__redis.sadd(Constants.REDIS_KEY_BIT_Z_OPEN_ORDER_IDS_PREFIX + ':' + coin, order_id)
            self.__redis.hmset(Constants.REDIS_KEY_BIT_Z_ORDER_PREFIX + ':' + coin + ':' + order_id, {
                'order_id': order_id,
                'order_type': BitZHelper.get_order_type(order_type),
                'symbol': coin,
                'order_price': price,
                'quantity': number,
                'filled_quantity': 0.0,
                'fee': 0.0,
                'created': time.time(),
                'status': Constants.ORDER_STATUS_NEW
            })

            trade_pair = extract_symbol(coin)
            exchange_coin = trade_pair[0]
            base_coin = trade_pair[1]
            if order_type == 'in':
                base_coin_delta = -1 * float(price) * float(number)
                self.update_position(base_coin, base_coin_delta)
            else:
                exchange_coin_delta = -1 * float(number)
                self.update_position(exchange_coin, exchange_coin_delta)
            return order_id
        print(result)
        return None

    def buy(self, coin, price, number):
        # type: (str, str, str) -> str
        return self.order('in', coin, price, number)

    def sell(self, coin, price, number):
        # type: (str, str, str) -> str
        return self.order('out', coin, price, number)

    def cancel_order(self, coin, order_id):
        # type: (str) -> object
        params = {'api_key': self.__api_key, 'id': str(order_id), 'timestamp': str(int(time.time())),
                  'nonce': '%06d' % random.randint(0, 999999)}
        params['sign'] = build_bit_z_sign(params, self.__secret_key)
        result = http_post(self.__url + BitZTrade.CANCEL_RESOURCE, params)
        if result['code'] == 0:
            self.__redis.srem(Constants.REDIS_KEY_BIT_Z_OPEN_ORDER_IDS_PREFIX + ':' + coin, order_id)
            self.__redis.sadd(Constants.REDIS_KEY_BIT_Z_CANCELLED_ORDER_IDS_PREFIX + ':' + coin, order_id)
            self.__redis.hset(Constants.REDIS_KEY_BIT_Z_ORDER_PREFIX + ':' + coin + ':' + order_id, 'status',
                              Constants.ORDER_STATUS_CANCELLED)
        return result

    def get_open_orders(self, coin):
        # type: (str) -> list
        """

        :param coin:
        :return:
        {
            'code': 0,
            'msg': 'Success',
            'data': [{
                'id': '85493197',
                'price': '0.00000214',
                'number': '10000.0000',
                'numberover': '10000.0000',
                'flag': 'sale',
                'status': '0',
                'datetime': '2018-01-28 09:30:42'
            }]
        }
        """

        params = {'api_key': self.__api_key, 'timestamp': str(int(time.time())),
                  'nonce': '%06d' % random.randint(0, 999999), 'coin': coin}
        params['sign'] = build_bit_z_sign(params, self.__secret_key)

        # {
        #     'code': 0,
        #     'msg': 'Success',
        #     'data': [{
        #         'id': '85493197',
        #         'price': '0.00000214',
        #         'number': '10000.0000',
        #         'numberover': '10000.0000',
        #         'flag': 'sale',
        #         'status': '0',
        #         'datetime': '2018-01-28 09:30:42'
        #     }]
        # }
        result = http_post(self.__url + BitZTrade.OPEN_ORDERS_RESOURCE, params)
        if result['code'] == 0:
            return result['data']
        print(result)
        return result

    def cancel_orders(self, coin, open_orders):
        for open_order in open_orders:
            print('cancel order', open_order)
            self.cancel_order(coin, open_order['id'])

    def cancel_all_orders(self, coin):
        open_orders = self.get_open_orders(coin)
        self.cancel_orders(coin, open_orders)
