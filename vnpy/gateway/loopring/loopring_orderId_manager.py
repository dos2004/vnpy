import os
import sys
from time import sleep

from vnpy.trader.setting import SETTINGS

class BaseOrderIdManager:
    def __init__(self):
        self.orderId = [None] * 256
    
    def get_orderId(self, tokenId):
        orderId = self.orderId[tokenId]
        self.orderId[tokenId] = self.orderId[tokenId] + 1
        return orderId

    def put_orderId(self, tokenId, orderId):
        self.orderId[tokenId] = orderId
