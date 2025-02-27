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
import os
import torch.cuda
from src.prompt import PromptGenerator
from src.spinner import Spinner
from src.executor import CodeExecutor
from src.build_RAG_private import preload_retriever
from src.local_llm import api_preload, api_generator, api_preload_deepseek, api_generator_deepseek
import openai
from openai import OpenAI
import time
import json

class Agent:
    def __init__(self,
                 initial_data_list,
                 output_dir,
                 initial_goal_description,
                 model_engine,
                 openai_api,
                 execute = True,
                 blacklist='',
                 gui_mode=False,
                 cpu=False,
                 rag=False):
        self.initial_data_list = initial_data_list
        self.initial_goal_description = initial_goal_description
        self.tasks = []
        self.update_data_lists = [_ for _ in initial_data_list]
        self.output_dir = output_dir
        self.update_data_lists.append(f'{output_dir}: all outputs should be stored under this dir')
        self.model_engine = model_engine
        self.rag = rag
        self.local_model_engines = ['codellama-7bi',
                                    'codellama-13bi',
                                    'codellama-34bi',
                                    'llama2-7bc',
                                    'llama2-13bc',
                                    'llama2-70bc',
                                    'deepseek-6.7bi',
                                    'deepseek-7bi',
                                    'deepseek-33bi',
                                    'deepseek-67bc']
        self.gpt_model_engines = ['gpt-3.5-turbo',
                                  'gpt-4-turbo',
                                  'gpt-4',
                                  'gpt-4o',
                                  'gpt-4o-mini',
                                  'gpt-3.5-turbo-1106',
                                  'gpt-4-0613',
                                  'gpt-4-32k-0613',
                                  'gpt-4-1106-preview']
        self.ollama_engines = ['ollama_llama3.1']
        self.valid_model_engines = self.local_model_engines + self.gpt_model_engines
        self.openai_api = openai_api

        if self.rag:
            if self.model_engine in self.gpt_model_engines:
                self.retriever = preload_retriever(False,
                                                   self.openai_api,
                                                   PERSIST_DIR = "./softwares_database_RAG_openai",
                                                   SOURCE_DIR = "./softwares_database"
                                                   )
            else:
                self.retriever = preload_retriever(True,
                                                   None,
                                                   PERSIST_DIR="./softwares_database_RAG_local",
                                                   SOURCE_DIR="./softwares_database"
                                                   )
        else:
            self.retriever = None

        self.generator = PromptGenerator(blacklist=blacklist,
                                         engine = self.model_engine,
                                         rag = self.rag,
                                         retriever = self.retriever)
        self.global_round = 0
        self.execute = execute
        self.execute_success = True
        self.execute_info = ''
        self.code_executor = CodeExecutor()
        self.gui_mode = gui_mode
        self.cpu = cpu

        if self.model_engine.startswith('ollama_'):
            print('[INFO] using ollama engine!')
        elif self.model_engine not in self.valid_model_engines:
            print('[ERROR] model invalid, please check the model engine selected!')
            exit()

        # use gpt model
        if self.model_engine in self.gpt_model_engines:
            self.openai_client = OpenAI(
                # This is the default and can be omitted
                api_key=self.openai_api,
            )

        # load local model with ollama
        if self.model_engine.startswith('ollama_'):
            from langchain_community.llms import Ollama
            self.local_llm_generator = Ollama(model=self.model_engine.split('ollama_')[-1])

        # preload local model
        if 'llama' in self.model_engine and 'ollama_' not in self.model_engine:
            import torch.distributed as dist
            os.environ['MASTER_ADDR'] = 'localhost'
            os.environ['MASTER_PORT'] = '5678'
            if torch.cuda.is_available():
                dist.init_process_group(backend='nccl', init_method='env://', rank=0, world_size=1)
            else:
                dist.init_process_group(backend='gloo', init_method='env://', rank=0, world_size=1)

            if self.model_engine == 'codellama-7bi':
                self.local_llm_generator = api_preload(ckpt_dir='src/codellama-main/CodeLlama-7b-Instruct/',
                                        tokenizer_path='src/codellama-main/CodeLlama-7b-Instruct/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'codellama-13bi':
                self.local_llm_generator = api_preload(ckpt_dir='src/codellama-main/CodeLlama-13b-Instruct/one-gpu/',
                                        tokenizer_path='src/codellama-main/CodeLlama-13b-Instruct/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'codellama-34bi':
                self.local_llm_generator = api_preload(ckpt_dir='src/codellama-main/CodeLlama-34b-Instruct/one-gpu/',
                                        tokenizer_path='src/codellama-main/CodeLlama-34b-Instruct/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'llama2-7bc':
                self.local_llm_generator = api_preload(ckpt_dir='src/llama-main/llama-2-7b-chat/',
                                        tokenizer_path='src/llama-main/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'llama2-13bc':
                self.local_llm_generator = api_preload(ckpt_dir='src/llama-main/llama-2-13b-chat/one-gpu/',
                                        tokenizer_path='src/llama-main/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'llama2-70bc':
                self.local_llm_generator = api_preload(ckpt_dir='src/llama-main/llama-2-70b-chat/',
                                        tokenizer_path='src/llama-main/tokenizer.model',
                                        max_seq_len=4096)
            elif self.model_engine == 'deepseek-6.7bi':
                self.tokenizer, self.local_llm_generator = api_preload_deepseek(
                    ckpt_dir='src/deepseek/deepseek-coder-6.7b-instruct/',
                    tokenizer_path='src/deepseek/deepseek-coder-6.7b-instruct/',
                    cpu = self.cpu
                )
            elif self.model_engine == 'deepseek-7bi':
                self.tokenizer, self.local_llm_generator = api_preload_deepseek(
                    ckpt_dir='src/deepseek/deepseek-coder-7b-instruct-v1.5/',
                    tokenizer_path='src/deepseek/deepseek-coder-7b-instruct-v1.5/',
                    cpu = self.cpu
                )
            elif self.model_engine == 'deepseek-33bi':
                self.tokenizer, self.local_llm_generator = api_preload_deepseek(
                    ckpt_dir='src/deepseek/deepseek-coder-33b-instruct/',
                    tokenizer_path='src/deepseek/deepseek-coder-33b-instruct/',
                    cpu = self.cpu
                )
            elif self.model_engine == 'deepseek-67bc':
                self.tokenizer, self.local_llm_generator = api_preload_deepseek(
                    ckpt_dir='src/deepseek/deepseek-llm-67b-chat/',
                    tokenizer_path='src/deepseek/deepseek-llm-67b-chat/',
                    cpu = self.cpu
                )


    def get_single_response(self, prompt):

        # use openai
        if self.model_engine in self.gpt_model_engines:

            if self.model_engine in ['gpt-3.5-turbo-1106', 'gpt-4-1106-preview']:
                response = self.openai_client.chat.completions.create(
                    model=self.model_engine,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "user", "content": str(prompt)}],
                    max_tokens=1024,
                    temperature=0,
                )
            else:
                response = self.openai_client.chat.completions.create(
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
            response_message = response.choices[0].message.content
        elif self.model_engine in self.local_model_engines:
            instructions = [
                [
                    {
                        "role": "user",
                        "content": str(prompt),
                    }
                ],
            ]
            if 'deepseek' in self.model_engine:
                results = api_generator_deepseek(instructions = instructions,
                                       tokenizer = self.tokenizer,
                                       generator = self.local_llm_generator,
                                       max_new_tokens=4096,
                                       top_k=50,
                                       top_p=0.95)
            elif 'llama' in self.model_engine:
                results = api_generator(instructions=instructions,
                                        generator=self.local_llm_generator,
                                        temperature=0.6)
            response_message = results[0]['generation']['content']
        elif self.model_engine.startswith('ollama_'):
            response_message = self.local_llm_generator.invoke(str(prompt))
        return response_message

    def valid_json_response(self, response_message):
        if not os.path.isdir(f'{self.output_dir}'):
            os.makedirs(f'{self.output_dir}')
        try:
            with open(f'{self.output_dir}/{self.global_round}_response.json', 'w') as w:
                json.dump(json.loads(response_message), w)
            json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
        except:
            print('[INVALID RESSPONSE]\n', response_message)
            return False
        return True

    def valid_json_response_executor(self, response_message):
        if not os.path.isdir(f'{self.output_dir}'):
            os.makedirs(f'{self.output_dir}')
        try:
            with open(f'{self.output_dir}/executor_response.json', 'w') as w:
                json.dump(json.loads(response_message), w)
            tmp_data = json.load(open(f'{self.output_dir}/executor_response.json'))
            if str(tmp_data['stat']) not in ['0', '1']:
                return False
        except:
            print('[INVALID RESSPONSE]\n', response_message)
            return False
        return True

    def process_tasks(self, response_message):
        self.tasks = response_message['plan']

    def find_json(self, response_message):
        if "```json\n" in response_message:
            start_index = response_message.find("{")
            end_index = response_message.rfind("}") + 1
            # 提取 JSON 部分
            return response_message[start_index:end_index]
        elif "```bash\n" in response_message:
            start_index = response_message.find("```bash\n")
            end_index = response_message.find("```\n")
            return str({'tool':'','code':response_message[start_index:end_index].lstrip('```bash\n')})
        else:
            start_index = response_message.find("{")
            end_index = response_message.rfind("}") + 1
            # 提取 JSON 部分
            return response_message[start_index:end_index]

    def execute_code(self, response_message):
        if not os.path.isdir(f'{self.output_dir}'):
            os.makedirs(f'{self.output_dir}')
        try:
            with open(f'{self.output_dir}/{self.global_round}.sh', 'w') as w:
                w.write(response_message['code'])
            if self.execute:
                self.last_execute_code = response_message['code']
                executor_info = self.code_executor.execute(bash_code_path=f'{self.output_dir}/{self.global_round}.sh')
                if len(executor_info) == 0:
                    execute_statu, execute_info = True, 'No error message'
                else:
                    executor_response_message = self.get_single_response(self.generator.get_executor_prompt(executor_info=executor_info))
                    print('[CHECKING EXECUTION RESULTS]\n')
                    if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                        executor_response_message = self.find_json(executor_response_message)
                    max_tries = 10
                    n_tries = 0
                    while not self.valid_json_response_executor(executor_response_message):
                        print(f'[EXECUTOR RESPONSE CHECKING TEST #{n_tries}/{max_tries}]')
                        if 'gpt' in self.model_engine:
                            time.sleep(20)
                        executor_response_message = self.get_single_response(
                            self.generator.get_executor_prompt(executor_info=executor_info))
                        print('[CHECKING EXECUTION RESULTS]\n')
                        if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                            executor_response_message = self.find_json(executor_response_message)
                        if n_tries > max_tries:
                            executor_response_message = {'stat':0, 'info':'None'}
                            break
                        n_tries += 1
                    executor_response_message = json.load(open(f'{self.output_dir}/executor_response.json'))
                    execute_statu, execute_info = executor_response_message['stat'], executor_response_message['info']
                    #execute_statu, execute_info = executor_response_message['stat'], executor_info
                #os.system(f'bash {self.output_dir}/{self.global_round}.sh')
                return bool(int(execute_statu)), execute_info
            return True, 'Success without executing'
        except Exception as e:
            return False, e

    def run_plan_phase(self):
        # initial prompt
        init_prompt = self.generator.get_prompt(
            data_list=self.initial_data_list,
            goal_description=self.initial_goal_description,
            global_round=self.global_round,
            execute_success=self.execute_success,
            execute_info=self.execute_info
        )

        INFO_STR_USER = self.generator.format_user_prompt(init_prompt, self.global_round, self.gui_mode)
        if self.gui_mode:
            print('[AI Thinking...]')
            response_message = self.get_single_response(init_prompt)
            if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                response_message = self.find_json(response_message)
            while not self.valid_json_response(response_message):
                print(f'[Invalid Response, Waiting for 20s and Retrying...]')
                print(f'invalid response: {response_message}')
                if 'gpt' in self.model_engine:
                    time.sleep(20)
                response_message = self.get_single_response(init_prompt)
            response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
        else:
            with Spinner(f'\033[32m[AI Thinking...]\033[0m'):
                response_message = self.get_single_response(init_prompt)
                if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                    response_message = self.find_json(response_message)
                while not self.valid_json_response(response_message):
                    print(f'\033[32m[Invalid Response, Waiting for 20s and Retrying...]\033[0m')
                    print(f'invalid response: {response_message}')
                    if 'gpt' in self.model_engine:
                        time.sleep(20)
                    response_message = self.get_single_response(init_prompt)
                response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
        INFO_STR_AI = self.generator.format_ai_response(response_message, self.gui_mode)

        # process tasks
        self.process_tasks(response_message)
        self.generator.set_tasks(self.tasks)
        self.generator.add_history(None, self.global_round, self.update_data_lists)
        self.global_round += 1

        if self.execute == False:
            time.sleep(15)
        else:
            pass

    def run_code_generation_phase(self):
        # finish task one-by-one with code
        # print('[DEBUG] ', self.tasks)
        while len(self.tasks) > 0:
            task = self.tasks.pop(0)

            prompt = self.generator.get_prompt(
                data_list=self.update_data_lists,
                goal_description=task,
                global_round=self.global_round,
                execute_success=self.execute_success,
                execute_info=self.execute_info
            )

            self.first_prompt = True
            self.execute_success = False
            while self.execute_success == False:

                if self.first_prompt == False:
                    prompt = self.generator.get_prompt(
                        data_list=self.update_data_lists,
                        goal_description=task,
                        global_round=self.global_round,
                        execute_success=self.execute_success,
                        execute_info=self.execute_info,
                        last_execute_code=self.last_execute_code
                    )

                INFO_STR_USER = self.generator.format_user_prompt(prompt, self.global_round, self.gui_mode)
                if self.gui_mode:
                    print('[AI Thinking...]')
                    response_message = self.get_single_response(prompt)
                    if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                        response_message = self.find_json(response_message)
                    while not self.valid_json_response(response_message):
                        print(f'[Invalid Response, Waiting for 20s and Retrying...]')
                        print(f'invalid response: {response_message}')
                        if 'gpt' in self.model_engine:
                            time.sleep(20)
                        response_message = self.get_single_response(prompt)
                    response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
                else:
                    with Spinner(f'\033[32m[AI Thinking...]\033[0m'):
                        response_message = self.get_single_response(prompt)
                        if 'llama' in self.model_engine or 'deepseek' in self.model_engine:
                            response_message = self.find_json(response_message)
                        while not self.valid_json_response(response_message):
                            print(f'\033[32m[Invalid Response, Waiting for 20s and Retrying...]\033[0m')
                            print(f'invalid response: {response_message}')
                            if 'gpt' in self.model_engine:
                                time.sleep(20)
                            response_message = self.get_single_response(prompt)
                        response_message = json.load(open(f'{self.output_dir}/{self.global_round}_response.json'))
                INFO_STR_AI = self.generator.format_ai_response(response_message, self.gui_mode)

                # execute code
                if self.gui_mode:
                    print('[AI Executing codes...]')
                    print(f'[Execute Code Start]')
                    execute_success, execute_info = self.execute_code(response_message)
                    self.execute_success = execute_success
                    self.execute_info = execute_info
                    print('[Execute Code Finish]', self.execute_success, self.execute_info)

                    if self.execute_success:
                        print(f'[Execute Code Success!]')
                        self.execute_info = ''
                    else:
                        print(f'[Execute Code Failed!]')
                        self.first_prompt = False
                else:
                    with Spinner(f'\033[32m[AI Executing codes...]\033[0m'):
                        print(f'\033[32m[Execute Code Start]\033[0m')
                        execute_success, execute_info = self.execute_code(response_message)
                        self.execute_success = execute_success
                        self.execute_info = execute_info
                        print('\033[32m[Execute Code Finish]\033[0m', self.execute_success, self.execute_info)

                        if self.execute_success:
                            print(f'\033[32m[Execute Code Success!]\033[0m')
                            self.execute_info = ''
                        else:
                            print(f'\033[31m[Execute Code Failed!]\033[0m')
                            self.first_prompt = False

            self.generator.add_history(task, self.global_round, self.update_data_lists, code=response_message['code'])
            self.global_round += 1
            if self.execute == False:
                time.sleep(15)

    def run(self):
        self.run_plan_phase()
        self.run_code_generation_phase()
        print(f'\033[31m[Job Finished! Cheers!]\033[0m')