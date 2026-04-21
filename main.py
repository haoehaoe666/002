import json
import time
import argparse
import os
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


from utils import reserve, get_user_credentials

get_current_time = lambda action: (
    time.strftime("%H:%M:%S", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%H:%M:%S", time.localtime(time.time()))
)
get_current_dayofweek = lambda action: (
    time.strftime("%A", time.localtime(time.time() + 8 * 3600))
    if action
    else time.strftime("%A", time.localtime(time.time()))
)


SLEEPTIME = 0.2  # 每次抢座的间隔
ENDTIME = "20:01:00"  # 根据学校的预约座位时间+1min即可

ENABLE_SLIDER = True  # 是否有滑块验证
MAX_ATTEMPT = 3  # 最大尝试次数
RESERVE_NEXT_DAY = False  # 预约明天而不是今天的


def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number should match the number of config")
    if success_list is None:
        success_list = [False] * len(users)
    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )
        if current_dayofweek not in daysofweek:
            logging.info("Today not set to reserve")
            continue
        if not success_list[index]:
            logging.info(
                f"----------- {username} -- {times} -- {seatid} try -----------"
            )
            s = reserve(
                sleep_time=SLEEPTIME,
                max_attempt=MAX_ATTEMPT,
                enable_slider=ENABLE_SLIDER,
                reserve_next_day=RESERVE_NEXT_DAY,
            )
            s.get_login_status()
            s.login(username, password)
            s.requests.headers.update({"Host": "office.chaoxing.com"})
            suc = s.submit(times, roomid, seatid, action)
            success_list[index] = suc
    return success_list


def main(users, action=False):
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)

    current_dayofweek = get_current_dayofweek(action)
    today_reservation_num = sum(1 for d in users if current_dayofweek in d.get("daysofweek"))
    success_list = [False] * len(users)

    import datetime
    # 统一北京时间
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8) if action else datetime.datetime.now()

    # --- 阶段一：秒杀预热 (20:00 前运行) ---
    if now.hour < 20:
        logging.info("检测到未到 20:00，进入准点秒杀模式...")
        sessions = []
        for index, user in enumerate(users):
            username, password, times, roomid, seatid, daysofweek = user.values()
            if current_dayofweek not in daysofweek:
                sessions.append(None)
                continue
            if action:
                username, password = usernames.split(",")[index], passwords.split(",")[index]

            s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
            s.get_login_status(); s.login(username, password)
            s.requests.headers.update({"Host": "office.chaoxing.com"})
            sessions.append({"session": s, "times": times, "roomid": roomid, "seatid": seatid, "parm": None})

        preheated = False
        while True:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=8) if action else datetime.datetime.now()
            # 19:59:50 开始解验证码
            if now.hour == 19 and now.minute == 59 and now.second >= 50 and not preheated:
                for idx, data in enumerate(sessions):
                    if data and not success_list[idx]:
                        data["parm"], _ = data["session"].pre_heat(data["times"], data["roomid"], data["seatid"], action)
                preheated = True
                logging.info("验证码已预解，子弹上膛...")
            # 20:00:00 准时开火 (修改为 5 次 0.1 秒连发)
            if now.hour >= 20:
                logging.info("时间到，开启 0.1s 高频连发模式！")
                for i in range(5):  # 连发 5 次
                    logging.info(f"--- 正在进行第 {i+1} 轮连发 ---")
                    all_success = True
                    
                    for idx, data in enumerate(sessions):
                        # 如果该账号配置有效，且还没抢到
                        if data and data["parm"] and not success_list[idx]:
                            success_list[idx] = data["session"].fire(data["parm"], data["times"])
                        
                        # 检查是否所有账号都抢到了
                        if data and not success_list[idx]:
                            all_success = False
                            
                    if all_success:
                        logging.info("所有账号均在连发阶段秒杀成功！")
                        break  # 如果都抢到了，提前结束连发
                        
                    time.sleep(0.1)  # 连发间隔 0.1 秒
                    
                break  # 5 次连发打完，跳出预热等待循环，进入下方的常规重试兜底
            time.sleep(0.01)

    # --- 阶段二：常规重试 (兜底) ---
    logging.info(f"秒杀结束。当前状态: {success_list}。进入循环重试直到 {ENDTIME}")
    current_time = get_current_time(action)
    while current_time < ENDTIME:
        if sum(success_list) == today_reservation_num:
            logging.info("任务全部完成！")
            return # 这里要正确缩进，退出整个 main
        success_list = login_and_reserve(users, usernames, passwords, action, success_list)
        current_time = get_current_time(action)
        time.sleep(SLEEPTIME)
def debug(users, action=False):
    logging.info(
        f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_NEXT_DAY: {RESERVE_NEXT_DAY}"
    )
    suc = False
    logging.info(f" Debug Mode start! , action {'on' if action else 'off'}")
    if action:
        usernames, passwords = get_user_credentials(action)
    current_dayofweek = get_current_dayofweek(action)
    for index, user in enumerate(users):
        username, password, times, roomid, seatid, daysofweek = user.values()
        if type(seatid) == str:
            seatid = [seatid]
        if action:
            username, password = (
                usernames.split(",")[index],
                passwords.split(",")[index],
            )
        if current_dayofweek not in daysofweek:
            logging.info("Today not set to reserve")
            continue
        logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=RESERVE_NEXT_DAY,
        )
        s.get_login_status()
        s.login(username, password)
        s.requests.headers.update({"Host": "office.chaoxing.com"})
        suc = s.submit(times, roomid, seatid, action)
        if suc:
            return


def get_roomid(args1, args2):
    username = input("请输入用户名：")
    password = input("请输入密码：")
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_NEXT_DAY,
    )
    s.get_login_status()
    s.login(username=username, password=password)
    s.requests.headers.update({"Host": "office.chaoxing.com"})
    encode = input("请输入deptldEnc：")
    s.roomid(encode)


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    parser = argparse.ArgumentParser(prog="Chao Xing seat auto reserve")
    parser.add_argument("-u", "--user", default=config_path, help="user config file")
    parser.add_argument(
        "-m",
        "--method",
        default="reserve",
        choices=["reserve", "debug", "room"],
        help="for debug",
    )
    parser.add_argument(
        "-a",
        "--action",
        action="store_true",
        help="use --action to enable in github action",
    )
    args = parser.parse_args()
    func_dict = {"reserve": main, "debug": debug, "room": get_roomid}
    with open(args.user, "r+") as data:
        usersdata = json.load(data)["reserve"]
    func_dict[args.method](usersdata, args.action)
