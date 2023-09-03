#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
@Project ：Auto-BioinfoGPT 
@File    ：agent.py
@Author  ：Juexiao Zhou
@Contact : juexiao.zhou@gmail.com
@Date    ：2023/5/3 13:24 
'''
import os.path

from src.prompt import PromptGenerator
from src.spinner import Spinner
import openai
import time
import json

class Agent:
    def __init__(self,initial_data_list, output_dir, initial_goal_description, model_engine, openai_api, excute = True):
        self.initial_data_list = initial_data_list
        self.initial_goal_description = initial_goal_description
        self.tasks = []
        self.update_data_lists = [_ for _ in initial_data_list]
        self.output_dir = output_dir
        self.update_data_lists.append(f'{output_dir}: all outputs should be stored under this dir')
        self.generator = PromptGenerator()
        self.model_engine = model_engine
        self.global_round = 0
        self.excute = excute
        openai.api_key = openai_api

    def get_single_response(self, prompt):

        response = openai.ChatCompletion.create(
            model=self.model_engine,
              messages=[
                {"role": "user", "content": str(prompt)}],
            max_tokens=1024,
            temperature=0,
        )

        """
        {
          "choices": [
            {
              "finish_reason": "stop",
              "index": 0,
              "message": {
                "content": "Hello! As an AI language model, I don't have emotions, but I'm functioning well. I'm here to assist you with any questions or tasks you may have. How can I help you today?",
                "role": "assistant"
              }
            }
          ],
          "created": 1683014436,
          "id": "chatcmpl-7BfE4AdTo5YlSIWyMDS6nL6CYv5is",
          "model": "gpt-3.5-turbo-0301",
          "object": "chat.completion",
          "usage": {
            "completion_tokens": 42,
            "prompt_tokens": 20,
            "total_tokens": 62
          }
        }
        """

        response_message = response['choices'][0]['message']['content']
        return response_message

    def valid_json_response(self, response_message):
        if not os.path.isdir(f'{self.output_dir}'):
            os.makedirs(f'{self.output_dir}')
        with open(f'{self.output_dir}/{self.global_round}_response.json', 'w') as w:
            w.write(response_message)
        try:
            json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
        except:
            print('[INVALID RESSPONSE]\n', response_message)
            return False
        return True

    def process_tasks(self, response_message):
        self.tasks = response_message['plan']

    def excute_code(self, response_message):
        if not os.path.isdir(f'{self.output_dir}'):
            os.makedirs(f'{self.output_dir}')
        try:
            with open(f'{self.output_dir}/{self.global_round}.sh', 'w') as w:
                w.write(response_message['code'])
            if self.excute:
                os.system(f'bash {self.output_dir}/{self.global_round}.sh')
            return True
        except:
            return False

    def run(self):

        # initial prompt
        init_prompt = self.generator.get_prompt(
            data_list=self.initial_data_list,
            goal_description=self.initial_goal_description,
            global_round=self.global_round)

        self.generator.format_user_prompt(init_prompt, self.global_round)
        with Spinner(f'\033[32m[AI Thinking...]\033[0m'):
            response_message = self.get_single_response(init_prompt)
            while not self.valid_json_response(response_message):
                print(f'\033[32m[Invalid Response, Waiting for 20s and Retrying...]\033[0m')
                print(f'invalid response: {response_message}')
                time.sleep(20)
                response_message = self.get_single_response(init_prompt)
            response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
        self.generator.format_ai_response(response_message)
        # process tasks
        self.process_tasks(response_message)
        self.generator.set_tasks(self.tasks)
        self.generator.add_history(None, self.global_round, self.update_data_lists)
        self.global_round += 1

        if self.excute == False:
            time.sleep(15)
        else:
            pass

        # finish task one-by-one with code
        #print('[DEBUG] ', self.tasks)
        while len(self.tasks) > 0:
            task = self.tasks.pop(0)
            prompt = self.generator.get_prompt(
                data_list=self.update_data_lists,
                goal_description=task,
                global_round=self.global_round)
            self.generator.format_user_prompt(prompt=prompt, global_round=self.global_round)
            with Spinner(f'\033[32m[AI Thinking...]\033[0m'):
                response_message = self.get_single_response(prompt)
                while not self.valid_json_response(response_message):
                    print(f'\033[32m[Invalid Response, Waiting for 20s and Retrying...]\033[0m')
                    print(f'invalid response: {response_message}')
                    time.sleep(20)
                    response_message = self.get_single_response(prompt)
                response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
            self.generator.format_ai_response(response_message)

            # excute code
            with Spinner(f'\033[32m[AI Excuting codes...]\033[0m'):
                excute_success = self.excute_code(response_message)

            self.generator.add_history(task, self.global_round, self.update_data_lists, code=response_message['code'])
            self.global_round += 1
            if self.excute == False:
                time.sleep(15)
            else:
                pass

        print(f'\033[31m[Job Finished! Cheers!]\033[0m')