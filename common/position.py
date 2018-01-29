from abc import abstractmethod

import redis

from common.order import Order
from constants import Constants


class Position(object):
    def __init__(self, init_positions: dict, position_redis_key: str, open_order_redis_key_prefix: str,
                 cancelled_order_redis_key_prefix: str, closed_order_redis_key_prefix: str,
                 order_redis_key_prefix: str, trade_pair_redis_key: str):
        self.__redis = redis.StrictRedis()
        self.__position_redis_key = position_redis_key
        self.__redis.hmset(position_redis_key, init_positions)
        self.__open_order_redis_key_prefix = open_order_redis_key_prefix
        self.__cancelled_order_redis_key_prefix = cancelled_order_redis_key_prefix
        self.__closed_order_redis_key_prefix = closed_order_redis_key_prefix
        self.__order_redis_key_prefix = order_redis_key_prefix
        self.__trade_pair_redis_key = trade_pair_redis_key

    @abstractmethod
    def get_orders(self, symbol: str, order_ids: list[str]) -> list[Order]:
        pass

    def update_position(self, coin: str, delta: float):
        quantity = self.__redis.hmget(self.__position_redis_key, coin)
        if quantity is None:
            quantity = 0.0
        self.__redis.hset(self.__position_redis_key, coin, quantity + delta)

    def run(self):
        symbols = self.__redis.smembers(self.__trade_pair_redis_key)

        for symbol in symbols:
            open_order_ids = self.__redis.smembers(self.__open_order_redis_key_prefix + ':' + symbol)
            cancelled_order_ids = self.__redis.smembers(self.__cancelled_order_redis_key_prefix + ':' + symbol)
            order_ids = open_order_ids | cancelled_order_ids
            orders = self.get_orders(symbol, order_ids)
            for order in orders:
                order_id = order.get_order_id()
                filled_quantity = order.get_filled_quantity()
                avg_price = order.get_avg_price()
                fee = order.get_fee()
                status = order.get_status()
                self.__redis.hmset(Constants.REDIS_KEY_ALL_COIN_ORDER_PREFIX + ':' + symbol + ':' + order_id, {
                    'order_id': order_id,
                    'avg_price': avg_price,
                    'filled_quantity': filled_quantity,
                    'fee': fee,
                    'status': status
                })

                if status == Constants.ORDER_STATUS_FILLED or status == Constants.ORDER_STATUS_CANCELLED:
                    delta = -1 * fee
                    if order.is_buy():
                        delta += filled_quantity
                    else:
                        delta += -1 * filled_quantity

                    self.update_position(delta)

            for order_id in cancelled_order_ids:
                self.__redis.srem(self.__cancelled_order_redis_key_prefix + ':' + symbol, order_id)
                self.__redis.sadd(self.__closed_order_redis_key_prefix + ':' + symbol, order_id)