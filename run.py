import argparse
import os

def get_args():
    parser = argparse.ArgumentParser(
        description='Process RMIT student cards and output their attributes to a CSV file.')
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument('-b', '--batch', help="Parse all images in the directory given")
    mode.add_argument('-d', '--debug', nargs=argparse.REMAINDER, help="Run the listed images in replay/debug mode")
    mode.add_argument('--dev', action="store_true", help="Run the program in development mode")
    if not os.getenv("OCR_AUTH_KEY"):
        parser.add_argument("gcloud_token", help="Required when the OCR_AUTH_KEY environment var is not present")
    else:
        parser.add_argument("--gcloud_token", help="Required when the OCR_AUTH_KEY environment var is not present")
    return parser.parse_args()


def args_to_env():
    args = get_args()
    if args.gcloud_token:
        os.putenv("OCR_AUTH_KEY", args.gcloud_token)


"""
This needs to be at the top of the file otherwise the environment change will not propagate.
"""
if __name__ == '__main__':
    args_to_env()

""" Native Python Libs"""
import time
import traceback
from datetime import datetime, timedelta
from threading import Thread
from tkinter import *

""" Third party Libraries """
import cv2


""" Local file imports """
import Config
import utilities.io_functions as io
from Card import Card
from functions import output_card_to_image, cv_2_pil
from ocr_detection import barcode
from user_inteface.State import State, STATES
from user_inteface.window import Window
from utilities.Cursor import Cursor


# TODO: Investigate records not being saved to CSV
def demo():
    root = Tk()
    with State(camera=cv2.VideoCapture(Config.target_camera)) as state:
        window = Window(root)

        def tick(e=None):
            state.snap()
            window.output.update_status(state)
            if state == STATES.CAPTURE:
                # state.dim_frame()
                window.update_camera(state.frame, None)
                root.after(10, tick)
                return

            state.find_barcode()
            if state == STATES.ERRORED:
                root.after(10, tick)
                return
            window.update_camera(state.frame, state.debug_frame)
            if state == STATES.DETECT and state.modified < datetime.now() - timedelta(seconds=1):
                root.after(2, process)
            root.after(10, tick)

        def process(e=None):
            if state == STATES.CAPTURE:
                return
            state.status = STATES.CAPTURE
            window.update_prelim(state.frame)

            def inner():
                try:
                    state.get_card()
                    if state == STATES.SUCCESS:
                        window.update_result(state.card, state.result_frame, success=save, cancel=do_abort)
                except Exception as ex:
                    print(ex)
                    state.status = STATES.ERRORED

            proc = Thread(target=inner)
            proc.start()
            # inner()

    def save(firstname=None, lastname=None, sid=None):
        if state == STATES.SUCCESS:
            if None not in (firstname, lastname, sid):
                io.insert_row(Config.OutputFormat, "{} {}".format(firstname, lastname), sid, )
            io.insert_record(Config.OutputFormat, state.card)
        state.reset_lifecycle()
        window.reset()

    def do_action(e=None):
        if state == STATES.SUCCESS:
            save()
        if state in (STATES.MONITOR, STATES.DETECT):
            process()

    def do_abort(e=None):
        state.reset_lifecycle()
        window.reset()

    root.bind("<space>", do_action)
    root.bind("esc", do_action)

    root.after(10, tick)
    root.mainloop()


def debug(args):
    root = Tk()
    w = Window(root)
    # camera = cv2.VideoCapture(Config.target_camera)

    cursor = Cursor(max=len(args))

    # def update_camera():
    #     if camera.isOpened():
    #         status, img = capture_2(camera)
    #         w.update_camera(img)
    #     root.after(5, update_camera)

    def update_capture(event=None):
        image_path, json_path = io.path_from_id(Config.OutputFormat(), args[cursor.index])
        while not os.path.exists(json_path):
            cursor.increment()
            image_path, json_path = io.path_from_id(Config.OutputFormat(), args[cursor.index])

        image = cv2.imread(image_path)
        bcimage, success, bounds = barcode.detect(image.copy())
        w.update_camera(bcimage)
        # card = Card.from_json_file(Config.OutputFormat(), json_path)
        # image = output_card_to_image(card, image)
        if success != -1:
            image = barcode.optimise(image, bounds)
            # recognise.do(image)

        w.update_prelim(image)

        cursor.increment()

    def on_save():
        pass

    root.bind("<space>", update_capture)

    # root.after(1, update_camera)
    root.mainloop()
    # camera.release()


def batch(target):
    paths = os.listdir(target)
    images = [path.strip(".temp.png") for path in paths if
              os.path.isfile(target + "/" + path) and path.endswith(".temp.png")]

    root = Tk()
    w = Window(root)

    cursor = Cursor(max=len(images), overflow=False)

    def update_camera():
        if cursor.index == 0:
            id = images[-1]
        else:
            id = images[cursor.index + 1]
        path, _ = io.path_from_id(Config.OutputFormat(), id)
        image = cv2.imread(path)
        debug_frame, success, bounds = barcode.detect(image)
        w.update_camera(image, debug_frame)
        root.after(250, update_camera)

    def update_capture(event=None):
        path, _ = io.path_from_id(Config.OutputFormat(), images[cursor.index])
        image = cv2.imread(path)
        w.update_prelim(image)

        def complete():
            b = cv2.imencode('.png', image)[1].tostring()
            # card = Card.from_image(Config.OutputFormat, b)
            card = Card.from_json_file(_)

            if card is not None:
                def save(firstname=None, lastname=None, sid=None):
                    print("Saving...")
                    override = time.strftime("%Y/%m/%d %H:%M", time.localtime(os.path.getctime(path)))
                    if None in (firstname, lastname, sid):

                        if not io.insert_record(Config.OutputFormat(), card, override):
                            print("Not Saved")
                    else:
                        io.insert_row(Config.OutputFormat, "{} {}".format(firstname, lastname), sid, override)
                    next()

                revised = output_card_to_image(card, image)

                w.update_result(card, cv_2_pil(revised), save, next)

        Thread(target=complete).start()

    def next():
        cursor.increment()
        update_capture()

    root.bind("<space>", next)

    root.after(1, update_camera)
    root.after(10, update_capture)
    root.mainloop()


def dev():
    root = Tk()
    w = Window(root, Config)

    # camera = cv2.VideoCapture(Config.target_camera)

    def update_camera():
        # if camera.isOpened():
        img = cv2.imread("./cache/20180624224050.temp.png")
        image, success, bounds = barcode.detect(img.copy())
        # img = detect_card(img)
        # if success > -1:
        #     optimal = optimise(image, bounds)
        w.update_prelim(image)
        w.update_camera(img)
        # root.after(10, update_camera)

    def update_capture(event=None):
        image = w.last_capture
        w.update_prelim(image)

        def complete():
            b = cv2.imencode('.png', image)[1].tostring()
            card = Card.from_image(Config.OutputFormat, b)
            if card is not None:
                revised = output_card_to_image(card, image)
                w.update_result(card, revised)

        # Thread(target=complete).start()

    def on_save():
        if w.label_info is not None:
            io.insert_record(Config.OutputFormat(), w.label_info.card)
        w.on_continue()

    def on_continue():
        w.hide_result()

    w.on_save = on_save

    root.bind("<space>", on_continue)

    root.after(10, update_camera)
    root.mainloop()
    # camera.release()


def run():
    args = get_args()
    # print(args)
    if args.debug:
        debug(args.debug)
    elif args.batch:
        batch(args.batch)
    elif args.dev:
        dev()
    else:
        try:
            demo()
        except Exception as ignored:
            traceback.print_exc()


run()
