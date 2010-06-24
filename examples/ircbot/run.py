#!/usr/bin/env python
# vim: fileencoding=utf8:et:sta:ai:sw=4:ts=4:sts=4

import traceback

import greenhouse
import logbot, opsbot, cmdbot

class MixBot(opsbot.OpsHolderBot, logbot.LogBot, cmdbot.CmdBot):
    pass


if __name__ == '__main__':
    greenhouse.add_exception_handler(traceback.print_exception)

    bot = MixBot(
            ("irc.freenode.net", 6667),
            "teeparktest",
            password="leverage",
            nickserv="NickServ",
            ops_password="gimmeh",
            rooms=["#teeparktestroom"])
    bot.run()
