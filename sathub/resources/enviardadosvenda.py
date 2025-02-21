# -*- coding: utf-8 -*-
#
# sathub/resources/enviardadosvenda.py
#
# Copyright 2015 Base4 Sistemas Ltda ME
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging

import json

import xmltodict

from flask_restful import Resource

from ..comum.config import basicConfig
from logging import debug, info

from ..comum.util import hexdump
from ..comum.util import instanciar_funcoes_sat
from ..comum.util import instanciar_numerador_sessao as instanciar_numerador
from ..custom import request_parser


logger = logging.getLogger('sathub.resource')

parser = request_parser()

parser.add_argument('dados_venda',
                    type=str,
                    required=True,
                    help=u'XML contendo os dados do CF-e de venda')


class EnviarDadosVenda(Resource):

    def obter_pedido(self, parametro):
        """
        Método que retornar o pedido/minuta contido no esqueleto do XML
        """
        xml = xmltodict.parse(parametro)
        return xml['CFe']['infCFe']['infAdic']['infCpl'].split(' ')[1]

    def venda_existe(self, vendas, dados_venda, pedido_atual):
        """
        Método que verifica se o cupom corrente já foi faturado
        """
        lista = ['pedido', 'cupom']
        for venda in vendas:
            xml, retorno_dict = (v for k, v in venda.items() if k not in lista)
            if dados_venda == xml:
                return retorno_dict
        return ''

    def monta_dicionario(self, tipo, retorno, objeto, dados, pedido):
        """
        Monta dicionário para inserir na lista de dicionários (arquivo json) e
        também atualiza o atributo de instancia `_ultimas_vendas`
        """
        list_retorno = retorno.split('|')

        if tipo == 'venda':

            # Montando dicionário da venda atual
            ultima_venda_dict = {
                'xml': dados,
                'pedido': pedido,
                'cupom': int(list_retorno[8][34:40]),
                'retorno': retorno
                }

            debug(
                f'VENDA - pedido: {pedido} - código: {list_retorno[1]} '
                f'cupom: {int(list_retorno[8][34:40])}'
                )

            # Enviando dicionário para arquivo
            objeto._escrever_dados_venda(ultima_venda_dict)

        elif tipo == 'erro':
            ultimo_erro = {
                'numero_sessao': list_retorno[0],
                'codigo_retorno': list_retorno[1],
                'pedido': pedido
            }

            debug(
                f'ERROR - numero sessão: {list_retorno[0]} - '
                f'código: {list_retorno[1]} pedido: {pedido}'
                )

            # Enviando dicionário para arquivo
            objeto._escrever_dados_erro(ultimo_erro)

    def post(self):

        while True:
            args = parser.parse_args()

            numero_caixa = args['numero_caixa']
            dados_venda = args['dados_venda']

            # Extraindo pedido do xml
            pedido_atual = self.obter_pedido(dados_venda)

            # Resgatando lista de dicionários com as últimas vendas
            numerador_instanciado = instanciar_numerador(numero_caixa)
            vendas = numerador_instanciado._ultimas_vendas

            # Instanciando objeto sathub
            fsat = instanciar_funcoes_sat(numero_caixa)

            # Consultando MFE
            if not fsat.consultar_sat():
                return 'Sem comunicação com o MFE!'

            # Verificando se o último cupom emitido é o mesmo do atual
            retorno_dict = self.venda_existe(vendas, dados_venda, pedido_atual)
            if retorno_dict:
                return dict(funcao='EnviarDadosVenda', retorno=retorno_dict)

            # Envio de cupom
            retorno = fsat.enviar_dados_venda(dados_venda)

            # Obtendo retorno do cupom (Se foi emitido ou não)
            status = retorno.split("|")[1]
            info(f'pedido: {pedido_atual} - código: {status}')
            if status == '06000':
                self.monta_dicionario(
                    'venda', retorno,
                    numerador_instanciado, dados_venda, pedido_atual
                )

            elif status == '06097':
                continue

            else:
                self.monta_dicionario(
                    'erro', retorno,
                    numerador_instanciado, dados_venda, pedido_atual
                )

            break

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Retorno "EnviarDadosVenda" '
                         '(numero_caixa=%s)\n%s',
                         numero_caixa, hexdump(retorno))

        return dict(funcao='EnviarDadosVenda', retorno=retorno)
