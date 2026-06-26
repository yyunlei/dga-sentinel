from fastapi import FastAPI, Request, Form  # 导入FastAPI库，Request用于处理请求，Form用于处理表单数据
from fastapi.responses import HTMLResponse  # 导入HTMLResponse，用于返回HTML响应
from fastapi.templating import Jinja2Templates  # 导入Jinja2Templates，用于模板渲染
from pydantic import BaseModel  # 导入BaseModel，用于定义请求数据的模型
from predict import bin_predict, multi_predict  # 导入自定义的二分类预测函数和多分类预测函数
from fastapi.staticfiles import StaticFiles  # 导入StaticFiles，用于提供静态文件（如CSS文件）

# 创建FastAPI应用实例
app = FastAPI()

# 为静态文件提供服务，将“static”目录挂载到/app/static路径
app.mount("/static", StaticFiles(directory="static"), name="static")

# 设置Jinja2模板引擎，指定模板文件所在的目录
templates = Jinja2Templates(directory="templates")

# 定义请求数据的模型（用于接收域名输入）
class DomainInput(BaseModel):
    domain_name: str  # 域名输入字段

# 主页的HTML响应，返回一个表单页面
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})  # 渲染index.html模板

# 用于处理表单提交，进行域名预测的API端点
@app.post("/predict/")
def predict_domain(request: Request, domain_name: str = Form(...)):  # 接收表单数据，获取域名
    # 二分类预测：判断域名是否为恶意
    binary_classifier = bin_predict(domain_name)  # 调用二分类预测函数，传入域名
    is_malware = binary_classifier.predict()  # 调用predict()方法进行预测

    if is_malware == 0:  # 如果预测结果是0，表示域名是良性（Benign）
        # 渲染结果页面，返回预测为"Benign"
        return templates.TemplateResponse("index.html", {"request": {}, "domain_name": domain_name, "prediction": "Benign"})

    # 如果是恶意域名，则进行多类别分类，识别恶意软件家族
    multi_classifier = multi_predict(domain_name)  # 调用多分类预测函数，传入域名
    '''
    malware_family = multi_classifier.predict()  # 获取恶意软件家族

    return templates.TemplateResponse("index.html", {"request": {}, "domain_name": domain_name, "prediction": "Malware", "malware_family": malware_family})
    '''
    # 获取前3个最可能的恶意软件家族
    top_3_predictions = multi_classifier.predict()  # 获取前3个预测结果

    # 渲染结果页面，显示"Malware"以及前3个预测的恶意软件家族
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,  # 请求对象
            "domain_name": domain_name,  # 域名
            "prediction": "Malware",  # 恶意软件预测
            "top_3_predictions": top_3_predictions  # 显示前3个预测结果
        }
    )

# 启动应用时使用的命令：uvicorn app:app --reload
