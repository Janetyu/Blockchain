import hashlib
import json
from textwrap import dedent
from time import time
from uuid import uuid4
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, request

class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # 创建创世区块
        self.new_block(previous_hash=1,proof=100)

    def register_node(self,address):
        '''
        向节点列表中添加一个新节点
        :param address: <str> Address of node. Eg. 'http://192.168.0.5:5000'
        :return: None
        '''
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self,chain):
        '''
        确定给定的区块链是否有效
        :param chain: <list> A blockchain
        :return: <bool> True if valid, False if not
        '''
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
           block = chain[current_index]
           print(f'{last_block}')
           print(f'{block}')
           print("\n-----------\n")
           # 检查块的散列是否正确
           if block['previous_hash'] != self.hash(last_block):
               return False

           # 检查工作证明是否正确
           if not self.valid_proof(last_block['proof'], block['proof']):
               return False

           last_block = block
           current_index += 1

        return True


    def resolve_conflicts(self):
        """
        共识算法解决冲突
        使用网络中最长的链.
        :return: <bool> True 如果链被取代, 否则为False
        """

        neighbours = self.nodes
        new_chain = None

        # 我们只是在寻找比我们的链条更长的链条
        max_length = len(self.chain)

        # 抓取并验证我们网络中所有节点的链
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # 检查长度是否更长，链条是否有效
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # 如果我们发现一条比我们的时间更长的新的有效链条，请替换我们的链条
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self,proof,previous_hash=None):
        # 创建一个新的区块并加入到链中
        '''
        proof：由工作证明算法给出的证明
        previous_hash：前一个Block的哈希
        return：一个新的区块
        '''
        block = {
            'index':len(self.chain)+1,
            'timestamp':time(),
            'transactions':self.current_transactions,
            'proof':proof,
            'previous_hash':previous_hash or self.hash(self.chain[-1])
        }

        # 重新设置当前区块的事务列表
        self.current_transactions = []

        self.chain.append(block)
        return block
    
    def new_transaction(self,sender,recipient,amount):
        # 生成新交易信息，信息将加入到下一个待挖的区块中
        '''
        sender:发件人的地址
        recipient:收件人的地址
        amount:交易数量
        return:将持有此交易的Block的索引
        '''
        self.current_transactions.append({
            'sender':sender,
            'recipient':recipient,
            'amount':amount,

        })

        return self.last_block['index']+ 1
    
    @staticmethod
    def hash(block):
        # 创建区块的哈希值
        '''
        生成块的hash值，格式为SHA-156
        block：字典类型的区块
        return：字符串
        '''
        #我们必须确保字典是有序的，否则我们将有不一致的哈希值
        block_string = json.dumps(block,sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        # 返回上一个区块
        return self.chain[-1]

    def proof_of_work(self,last_proof):
        '''
        简单的工作量证明:
            - 查找一个 p' 使得 hash(pp') 以4个0开头
            - p 是上一个块的证明,  p' 是当前的证明
            :param last_proof: <int>
            :return: <int>
        '''
        proof = 0
        while self.valid_proof(last_proof,proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof,proof):
        '''
            验证证明: 是否hash(last_proof, proof)以4个0开头?
            :param last_proof: <int> Previous Proof
            :param proof: <int> Current Proof
            :return: <bool> True if correct, False if not.
        '''
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

# 实例化我们的节点
app = Flask(__name__)

# 为此节点生成一个全球唯一的地址
node_identifier = str(uuid4()).replace('-','')

# 实例化区块链
blockchain = Blockchain()

# 创建/mine GET接口
@app.route('/mine',methods=['GET'])
def mine():
    # 我们运行工作证明算法以获得下一个证明...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # 给工作量证明的节点提供奖励.
    # 发送者为 "0" 表明是新挖出的币
    blockchain.new_transaction(
        sender = "0",
        recipient = node_identifier,
        amount = 1,
    )

    # 通过将其添加到链中来伪造新块
    block = blockchain.new_block(proof)

    response = {
        'message':"New Block Forged",
        'index':block['index'], 
        'transactions':block['transactions'],
        'proof':block['proof'],
        'previous_hash':block['previous_hash'],
    }

    return jsonify(response),200

# 创建/transactions/new POST接口,可以给接口发送交易数据.
@app.route('/transactions/new',methods=['POST'])
def new_transaction():
    values = request.get_json()

    # 检查必填字段是否在POST中
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
       return 'Missing values', 400

    # 创建一个新的事务
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message':f'Transaction will be added to Block {index}'}
    return jsonify(response),201

# 创建 /chain 接口, 返回整个区块链.
@app.route('/chain',methods=['GET'])
def full_chain():
    response = {
        'chain':blockchain.chain,
        'length':len(blockchain.chain),
    }
    return jsonify(response),200

# 用来注册节点
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
   values = request.get_json()

   nodes = values.get('nodes')
   if nodes is None:
       return "Error: Please supply a valid list of nodes", 400

   for node in nodes:
       blockchain.register_node(node)

   response = {
       'message': 'New nodes have been added',
       'total_nodes': list(blockchain.nodes),
   }
   return jsonify(response), 201

# 用来解决冲突
@app.route('/nodes/resolve', methods=['GET'])
def consensus():
   replaced = blockchain.resolve_conflicts()

   if replaced:
       response = {
           'message': 'Our chain was replaced',
           'new_chain': blockchain.chain
       }
   else:
       response = {
           'message': 'Our chain is authoritative',
           'chain': blockchain.chain
       }

   return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)



