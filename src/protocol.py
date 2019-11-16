"""
.. module:: schc
   :platform: Python, Micropython
"""
# ---------------------------------------------------------------------------

from gen_base_import import *  # used for now for differing modules in py/upy

# ---------------------------------------------------------------------------

from frag_recv import ReassemblerAckOnError
from frag_recv import ReassemblerNoAck
from frag_send import FragmentAckOnError
from frag_send import FragmentNoAck
import frag_msg
from compr_parser import *
from compr_core import Compressor, Decompressor


class Session:
    """ fragmentation/reassembly session manager
    session = [
        { "ruleID": n, "ruleLength", "dtag": n, "session": session }, ...
        ]
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.session_list = []

    def add(self, rule_id, rule_id_size, dtag, session):
        if self.get(rule_id, rule_id_size, dtag) is not None:
            print("ERROR: the session rid={}/{} dtag={} exists already".format(
                rule_id, rule_id_size, dtag))
            return False
        self.session_list.append({"rule_id": rule_id,
                                  "rule_id_size": rule_id_size, "dtag": dtag,
                                  "session": session})
        return True

    def get(self, rule_id, rule_id_size, dtag):
        for i in self.session_list:
            if (rule_id == i["rule_id"] and
                    rule_id_size == i["rule_id_size"] and dtag == i["dtag"]):
                return i["session"]
        return None


class debug_protocol:
    def _log(*arg):
        print(*arg)


class SCHCProtocol:
    """This class is the entry point for the openschc
    (in this current form, object composition is used)"""

    # def __init__(self, config, scheduler, schc_layer2, role="sender"):
    def __init__(self, config, system, layer2, layer3):
        self.config = config
        self.system = system
        self.scheduler = system.get_scheduler()
        self.layer2 = layer2
        self.layer3 = layer3
        self.layer2._set_protocol(self)
        self.layer3._set_protocol(self)
        self.default_frag_rule = None  # XXX: to be in  rule_manager
        self.compressor = Compressor(self)
        self.decompressor = Decompressor(self)
        self.fragment_session = Session(self)
        self.reassemble_session = Session(self)

    def _log(self, message):
        self.log("schc", message)

    def log(self, name, message):
        self.system.log(name, message)

    def set_rulemanager(self, rule_manager):
        self.rule_manager = rule_manager

    def schc_send(self, dst_L3addr, raw_packet):
        self._log("recv-from-L3 -> {} {}".format(dst_L3addr, raw_packet))
        context = self.rule_manager.find_context_bydstiid(dst_L3addr)
        print("raw_packet", raw_packet)

        P = Parser(debug_protocol)

        try:
            parsed_packet = P.parse(raw_packet, T_DIR_UP)
            pprint.pprint(parsed_packet[0])
        except:
            print("no parsing, try fragmentation")
            parsed_packet = None
            schc_packet = None

        if parsed_packet != None:
            # pass        # to be done
            rule = self.rule_manager.FindRuleFromPacket(parsed_packet[0], direction="UP")
            if rule is None:
                schc_packet = None
                # reject it.
                # self._log("Rejected. Not for SCHC packet, L3addr={}".format(
                #    dst_L3addr))
                # return
            else:
                if rule["Compression"] != []:
                    print(
                        "-------------------------------------- Compression Proccess -------------------------------------------")
                    print("selected rule is ", rule)
                    schc_packet = self.compressor.compress(rule, parsed_packet[0], parsed_packet[1], T_DIR_UP)
                    print(schc_packet)
                    schc_packet.display("bin")
                else:
                    schc_packet = None

        if schc_packet == None:
            packet_bbuf = BitBuffer(raw_packet)
        else:
            packet_bbuf = schc_packet

        # check if fragmentation is needed.
        if packet_bbuf.count_added_bits() < self.layer2.get_mtu_size():
            self._log("SCHC fragmentation is not needed. size={}".format(
                packet_bbuf.count_added_bits()))
            """ Changement à corriger
            args = (packet_bbuf.get_content(), context["devL2Addr"])
            """
            args = (packet_bbuf.get_content(), "*")
            self.scheduler.add_event(0, self.layer2.send_packet, args)
            return

        # fragmentation is required.
        frag_rule = self.rule_manager.FindFragmentationRule(self.layer2.devaddr)
        if frag_rule is None:
            self._log("Rejected the packet due to no fragmenation rule.")
            return
        # Do fragmenation
        print(
            "-------------------------------------- Fragmentation Proccess -------------------------------------------")
        rule = frag_rule
        context = None  # LT: don't know why context is needed, should be self.rule_manager which handle the context
        self._log("fragmentation rule_id={}".format(rule[T_RULEID]))
        session = self.new_fragment_session(context, rule)
        session.set_packet(packet_bbuf)
        self.fragment_session.add(rule[T_RULEID], rule[T_RULEIDLENGTH],
                                  session.dtag, session)
        session.start_sending()

    def new_fragment_session(self, context, rule):
        mode = rule[T_FRAG][T_FRAG_MODE]
        if mode == "noAck":
            session = FragmentNoAck(self, context, rule)  # XXX
        elif mode == "ackAlwayw":
            raise NotImplementedError(
                "{} is not implemented yet.".format(mode))
        elif mode == "ackOnError":
            session = FragmentAckOnError(self, context, rule)  # XXX
        else:
            raise ValueError("invalid FRMode: {}".format(mode))
        return session

    def new_reassemble_session(self, context, rule, dtag, dev_L2addr):
        mode = rule[T_FRAG][T_FRAG_MODE]
        if mode == "noAck":
            session = ReassemblerNoAck(self, context, rule, dtag, dev_L2addr)
        elif mode == "ackAlways":
            raise NotImplementedError("FRMode:", mode)
        elif mode == "ackOnError":
            session = ReassemblerAckOnError(self, context, rule, dtag,
                                            dev_L2addr)
        else:
            raise ValueError("FRMode:", mode)
        return session

    def schc_recv(self, dev_L2addr, raw_packet):
        # self._log("recv-from-L2 {} {}".format(dev_L2addr, raw_packet))

        frag_rule = self.rule_manager.FindFragmentationRule(dev_L2addr)

        # print(dev_L2addr)
        packet_bbuf = BitBuffer(raw_packet)
        # print("raw_packet", raw_packet)
        # print("schc packet", packet_bbuf)
        # print("frag_rule", frag_rule)

        # !IMPORTANT: This condition has to be changed by a context condition like in the last version
        if dev_L2addr == b"\xaa\xbb\xcc\xee":

            if frag_rule[T_FRAG][T_FRAG_PROF][T_FRAG_DTAG] > 0:
                dtag = packet_bbuf.get_bits(frag_rule[T_FRAG][T_FRAG_PROF][T_FRAG_DTAG],
                                            position=frag_rule[T_RULEIDLENGTH])
            else:
                dtag = None

            # find existing session for fragment or reassembly.
            session = self.reassemble_session.get(frag_rule[T_RULEID], frag_rule[T_RULEIDLENGTH], dtag)
            if session is not None:
                print("Reassembly session found", session)
            else:
                # no session is found.  create a new reassemble session.
                context = None
                session = self.new_reassemble_session(context, frag_rule, dtag,
                                                      dev_L2addr)
                self.reassemble_session.add(frag_rule[T_RULEID], frag_rule[T_RULEIDLENGTH],
                                            dtag, session)
                print("New reassembly session created", session)
            session.receive_frag(packet_bbuf, dtag)
            return

            self.process_decompress(packet_bbuf, dev_L2addr, direction=T_DIR_UP)

        elif dev_L2addr == b"\xaa\xbb\xcc\xdd":
            if frag_rule[T_FRAG][T_FRAG_PROF][T_FRAG_DTAG] > 0:
                dtag = packet_bbuf.get_bits(frag_rule[T_FRAG][T_FRAG_PROF][T_FRAG_DTAG],
                                            position=frag_rule[T_RULEIDLENGTH])
            else:
                dtag = None
            # find existing session for fragment or reassembly.
            session = self.fragment_session.get(frag_rule[T_RULEID], frag_rule[T_RULEIDLENGTH], dtag)
            print("rule.ruleID -> {},rule.ruleLength-> {}, dtag -> {}".format(frag_rule[T_RULEID],
                                                                              frag_rule[T_RULEIDLENGTH], dtag))
            if session is not None:
                print("Fragmentation session found", session)
                session.receive_frag(packet_bbuf, dtag)
            else:
                print("context exists, but no {} session for this packet {}".
                      format(dev_L2addr))
            return

    # def schc_recv(self, dev_L2addr, raw_packet):
    #     self._log("recv-from-L2 {} {}".format(dev_L2addr, raw_packet))
    #     # find context for the SCHC processing.
    #     # XXX
    #     # the receiver never knows if the packet from the device having the L2
    #     # addrss is encoded in SCHC.  Therefore, it has to search the db with
    #     # the field value of the packet.
    #     context = self.rule_manager.find_context_bydevL2addr(dev_L2addr)
    #     if context is None:
    #         # reject it.
    #         self._log("Rejected. Not for SCHC packet, sender L2addr={}".format(
    #                 dev_L2addr))
    #         return
    #     # find a rule in the context for this packet.
    #     packet_bbuf = BitBuffer(raw_packet)
    #     key, rule = self.rule_manager.find_rule_bypacket(context, packet_bbuf)
    #     if key == "fragSender":
    #         if rule["dtagSize"] > 0:
    #             dtag = packet_bbuf.get_bits(rule.get("dtagSize"),
    #                                 position=rule.get("ruleLength"))
    #         else:
    #             dtag = None
    #         # find existing session for fragment or reassembly.
    #         session = self.fragment_session.get(rule.ruleID,
    #                                             rule.ruleLength, dtag)
    #         if session is not None:
    #             print("Fragmentation session found", session)
    #             session.receive_frag(packet_bbuf, dtag)
    #         else:
    #             print("context exists, but no {} session for this packet {}".
    #                     format(key, dev_L2addr))
    #     elif key == "fragReceiver":
    #         if rule["dtagSize"] > 0:
    #             dtag = packet_bbuf.get_bits(rule.get("dtagSize"),
    #                                 position=rule.get("ruleLength"))
    #         else:
    #             dtag = None
    #         # find existing session for fragment or reassembly.
    #         session = self.reassemble_session.get(rule.ruleID,
    #                                             rule.ruleLength, dtag)
    #         if session is not None:
    #             print("Reassembly session found", session)
    #         else:
    #             # no session is found.  create a new reassemble session.
    #             session = self.new_reassemble_session(context, rule, dtag,
    #                                                   dev_L2addr)
    #             self.reassemble_session.add(rule.ruleID, rule.ruleLength,
    #                                         dtag, session)
    #             print("New reassembly session created", session)
    #         session.receive_frag(packet_bbuf, dtag)
    #     elif key == "comp":
    #         # if there is no reassemble rule, process_decompress() is directly
    #         # called from here.  Otherwise, it will be called from a reassemble
    #         # function().
    #         self.process_decompress(context, dev_L2addr, packet_bbuf)
    #     elif key is None:
    #         raise ValueError(
    #                 "context exists, but no rule found for L2Addr {}".
    #                 format(dev_L2addr))
    #     else:
    #         raise SystemError("should not come here.")

    def process_decompress(self, packet_bbuf, dev_L2addr, direction):
        rule = self.rule_manager.FindRuleFromSCHCpacket(packet_bbuf, dev_L2addr)
        if rule is None:
            # reject it.
            self._log("Rejected. Not rule compression for SCHC packet, sender L2addr={}".format(
                dev_L2addr))
            return

        if "Compression" not in rule:
            # reject it.
            self._log("Not compression parameters for SCHC packet, sender L2addr={}".format(
                dev_L2addr))
            return

        if rule["Compression"]:
            print("---------------------- Decompression ----------------------")
            print("---------------------- Decompression Rule-------------------------")
            self._log("compression rule_id={}".format(rule[T_RULEID]))
            print("receiver frag received:", packet_bbuf)
            print('rule {}'.format(rule))
            print("------------------------ Decompression ---------------------------")
            raw_packet = self.decompressor.decompress(packet_bbuf, rule, direction)
            print("---- Decompression result ----")
            print(raw_packet)
            args = (dev_L2addr, raw_packet)
            self.scheduler.add_event(0, self.layer3.recv_packet, args)

    # def process_decompress(self, context, dev_L2addr, schc_packet):
    #    self._log("compression rule_id={}".format(context["comp"]["ruleID"]))
    #    raw_packet = self.decompressor.decompress(context, schc_packet)
    #    args = (dev_L2addr, raw_packet)
    #    self.scheduler.add_event(0, self.layer3.recv_packet, args)
