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
    today_reservation_num = sum(
        1 for d in users if current_dayofweek in d.get("daysofweek")
    )
    success_list = [False] * len(users)

    import datetime
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8) if action else datetime.datetime.now()

    # 如果当前时间在 20:00 之前，则进入预热秒杀模式
    if now.hour < 20:
        logging.info("当前未到 20:00，进入预热和精确守时模式...")
        # 第一阶段：提前给所有需要抢座的账号完成登录操作
        sessions = []
        for index, user in enumerate(users):
            username, password, times, roomid, seatid, daysofweek = user.values()
            if current_dayofweek not in daysofweek:
                sessions.append(None)
                continue

            if action:
                username, password = usernames.split(",")[index], passwords.split(",")[index]

            s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_NEXT_DAY)
            s.get_login_status()
            s.login(username, password)
            s.requests.headers.update({"Host": "office.chaoxing.com"})
            sessions.append({
                "session": s, "times": times, "roomid": roomid, "seatid": seatid, "parm": None
            })

        # 第二阶段：时间监听，19:59:50 预热，20:00:00 开火
        preheated = False
        while True:
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=8) if action else datetime.datetime.now()

            # 到达 19:59:50，调用 utils.py 里的 pre_heat 解滑块
            if now.hour == 19 and now.minute == 59 and now.second >= 50 and not preheated:
                logging.info("时间到达 19:59:50，开始静默破解滑块...")
                for idx, data in enumerate(sessions):
                    if data and not success_list[idx]:
                        s = data["session"]
                        parm, _ = s.pre_heat(data["times"], data["roomid"], data["seatid"], action)
                        data["parm"] = parm
                preheated = True
                logging.info("子弹上膛完毕！进入 10 毫秒高频轮询，盯防 20:00:00...")

            # 准点击发，调用 utils.py 里的 fire
            if now.hour >= 20:
                logging.info(f"系统时间: {now.strftime('%H:%M:%S.%f')}，瞬间发射！")
                for idx, data in enumerate(sessions):
                    if data and data["parm"] and not success_list[idx]:
                        suc = data["session"].fire(data["parm"], data["times"])
                        success_list[idx] = suc
                break
            time.sleep(0.01) # 极低延迟轮询

        logging.info(f"秒杀阶段结束，当前成功状态: {success_list}")
        if sum(success_list) == today_reservation_num:
            logging.info("全部秒杀成功！退出程序。")
            return
        else:
            logging.info("部分座位预热秒杀失败，转入常规兜底重试流程...")

    # ==================== 常规兜底逻辑 ====================
    # 如果过了 20:00 才运行脚本，或者预热没抢到，老规矩继续循环
    current_time = get_current_time(action)
    attempt_times = 0
    while current_time < ENDTIME:
        attempt_times += 1
        success_list = login_and_reserve(
            users, usernames, passwords, action, success_list
        )
        print(
            f"attempt time {attempt_times}, time now {current_time}, success list {success_list}"
        )
        current_time = get_current_time(action)
        if success_list and sum(success_list) == today_reservation_num:
            print(f"reserved successfully!")
            return
            
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
