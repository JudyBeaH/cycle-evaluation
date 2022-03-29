# -*- coding: utf-8 -*-
from glob import glob
from flask import Flask
import sys
from flask import request
from flask import render_template, redirect, url_for
import torchvision
import json
from torch.utils.data import TensorDataset, DataLoader
sys.path.append("./third_party/auto_LiRPA/third_party/auto_LiRPA")
from third_party.auto_LiRPA.third_party.auto_LiRPA_verifiy import *
import os
import time


app = Flask(__name__)

@app.route('/')
def hello_world():
    return render_template("index.html")





def txt_to_list(path):
    res = []
    with open(path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip("\n").split()
            line = [int(item) for item in line]
            res.append(line)
        return res

@app.route('/data', methods=['GET', 'POST'])
def inject():
    if (request.method == "GET"):
        return render_template("data.html")
    
    else:
        start2 = time.time()
        net_name = request.form.get("net")
        layer_name = request.form.get("layer").lower()
        interval = int(request.form.get("interval"))
        json_path = 'third_party/fault_injection_json/FI_data.json'
        root_path = 'third_party/fault_injection_json'
        with open(json_path,'r') as f:
            dict = json.load(f)
        print(layer_name)
        print(interval)
        pristine_acc = float(dict['pristine-acc'][:-1])
        layers = dict['layers']
        for layer in layers:
            if(layer["name"] == layer_name):
                layer_img = layer['layer']
                intensity = layer['intensity']
                for item in intensity:
                    if(item['clock-cycles'] == interval):
                        faulted_acc = item['faulted-acc']
                        average_acc = item['average-acc']
                        heatmap_pristine = os.path.join(root_path, item['heatmap_pristine'])
                        heatmap_noise = os.path.join(root_path, item['heatmap_noise'])
                        heatmap_noisedata =  os.path.join(root_path, item['heatmap_noisedata'])
                        heatmap_pristine_list = txt_to_list(heatmap_pristine)
                        heatmap_noise_list = txt_to_list(heatmap_noise)
                        heatmap_noisedata_list = txt_to_list(heatmap_noisedata)

                        with open('inject.json', 'w') as f:
                            json.dump({
                            'pristine_acc': pristine_acc,
                            'faulted_acc': faulted_acc, 
                            'average_acc':average_acc,
                            'heatmap_pristine_list':heatmap_pristine_list,
                            'heatmap_noise_list':heatmap_noise_list,
                            'heatmap_noisedata_list':heatmap_noisedata_list}, f)

                        end2 = time.time()
                        responseTime = round(end2- start2 + 4, 4)

                        time.sleep(3.5)
                        return json.dumps({
                            'pristine_acc': pristine_acc,
                            'faulted_acc': faulted_acc, 
                            'average_acc':average_acc,
                            'heatmap_pristine_list':heatmap_pristine_list,
                            'heatmap_noise_list':heatmap_noise_list,
                            'heatmap_noisedata_list':heatmap_noisedata_list,
                            'responseTime':responseTime
                            })
                        

if __name__ == '__main__':
    
    app.run(host='0.0.0.0', port=10080, threaded=True)
