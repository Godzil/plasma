#!/usr/bin/env python3
#
# Reverse : Generate an indented asm code (pseudo-C) with colored syntax.
# Copyright (C) 2015    Joel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.    If not, see <http://www.gnu.org/licenses/>.
#

import struct

from capstone.x86 import (X86_INS_ADD, X86_INS_AND, X86_INS_CMP, X86_INS_DEC,
        X86_INS_IDIV, X86_INS_IMUL, X86_INS_INC, X86_INS_MOV, X86_INS_SHL,
        X86_INS_SHR, X86_INS_SUB, X86_INS_XOR, X86_OP_FP, X86_OP_IMM,
        X86_OP_INVALID, X86_OP_MEM, X86_OP_REG, X86_REG_EBP, X86_REG_EIP,
        X86_REG_RBP, X86_REG_RIP, X86_INS_CDQE, X86_INS_LEA, X86_INS_MOVSX,
        X86_INS_OR, X86_INS_NOT, X86_PREFIX_REP, X86_PREFIX_REPNE,
        X86_INS_TEST, X86_INS_JNS, X86_INS_JS, X86_INS_MUL, X86_INS_JP,
        X86_INS_JNP, X86_INS_JCXZ, X86_INS_JECXZ, X86_INS_JRCXZ,
        X86_INS_SAR, X86_INS_SAL, X86_INS_MOVZX, X86_INS_STOSB,
        X86_INS_STOSW, X86_INS_STOSD, X86_INS_STOSQ, X86_INS_MOVSB,
        X86_INS_MOVSW, X86_INS_MOVSD, X86_INS_MOVSQ, X86_INS_LODSB,
        X86_INS_LODSW, X86_INS_LODSD, X86_INS_LODSQ, X86_INS_CMPSB,
        X86_INS_CMPSW, X86_INS_CMPSD, X86_INS_CMPSQ, X86_INS_SCASB,
        X86_INS_SCASW, X86_INS_SCASD, X86_INS_SCASQ)

from lib.output import OutputAbs
from lib.utils import get_char, BYTES_PRINTABLE_SET
from lib.arch.x86.utils import (inst_symbol, is_call, is_jump, is_ret,
    is_uncond_jump, cond_symbol)


ASSIGNMENT_OPS = {X86_INS_XOR, X86_INS_AND, X86_INS_OR,
        X86_INS_SAR, X86_INS_SAL, X86_INS_SHR, X86_INS_SHL}


# After these instructions we need to add a zero
# example : jns ADDR -> if > 0
JMP_ADD_ZERO = {
    X86_INS_JNS,
    X86_INS_JS,
    X86_INS_JP,
    X86_INS_JNP,
    X86_INS_JCXZ,
    X86_INS_JECXZ,
    X86_INS_JRCXZ
}


INST_CHECK = {X86_INS_SUB, X86_INS_ADD, X86_INS_MOV, X86_INS_CMP,
    X86_INS_XOR, X86_INS_AND, X86_INS_SHR, X86_INS_SHL, X86_INS_IMUL,
    X86_INS_SAR, X86_INS_SAL, X86_INS_MOVZX,
    X86_INS_DEC, X86_INS_INC, X86_INS_LEA, X86_INS_MOVSX, X86_INS_OR}


INST_STOS = {X86_INS_STOSB, X86_INS_STOSW, X86_INS_STOSD, X86_INS_STOSQ}
INST_LODS = {X86_INS_LODSB, X86_INS_LODSW, X86_INS_LODSD, X86_INS_LODSQ}
INST_MOVS = {X86_INS_MOVSB, X86_INS_MOVSW, X86_INS_MOVSD, X86_INS_MOVSQ}
INST_CMPS = {X86_INS_CMPSB, X86_INS_CMPSW, X86_INS_CMPSD, X86_INS_CMPSQ}
INST_SCAS = {X86_INS_SCASB, X86_INS_SCASW, X86_INS_SCASD, X86_INS_SCASQ}

REP_PREFIX = {X86_PREFIX_REPNE, X86_PREFIX_REP}


class Output(OutputAbs):
    # Return True if the operand is a variable (because the output is
    # modified, we reprint the original instruction later)
    def _operand(self, i, num_op, hexa=False, show_deref=True):
        def inv(n):
            return n == X86_OP_INVALID

        op = i.operands[num_op]

        if op.type == X86_OP_IMM:
            imm = op.value.imm
            sec_name, is_data = self.binary.is_address(imm)

            if sec_name is not None:
                modified = False

                if self.ctx.sectionsname:
                    self._add("(")
                    self._section(sec_name)
                    self._add(") ")

                if imm in self.binary.reverse_symbols:
                    self._symbol(imm)
                    self._add(" ")
                    modified = True

                if imm in self.ctx.labels:
                    self._label(imm, print_colon=False)
                    self._add(" ")
                    modified = True

                if not modified:
                    self._add(hex(imm))

                if is_data:
                    s = self.binary.get_string(imm, self.ctx.max_data_size)
                    if s != "\"\"":
                        self._add(" ")
                        self._string(s)

                return modified

            elif op.size == 1:
                self._string("'%s'" % get_char(imm))
            elif hexa:
                self._add(hex(imm))
            else:
                self._add(str(imm))

                if imm > 0:
                    if op.size == 4:
                        packed = struct.pack("<L", imm)
                    elif op.size == 8:
                        packed = struct.pack("<Q", imm)
                    else:
                        return False
                    if set(packed).issubset(BYTES_PRINTABLE_SET):
                        self._string(" \"" + "".join(map(chr, packed)) + "\"")
                        return False

                # returns True because capstone print immediate in hexa
                # it will be printed in a comment, sometimes it's better
                # to have the value in hexa
                return True

            return False

        elif op.type == X86_OP_REG:
            self._add(i.reg_name(op.value.reg))
            return False

        elif op.type == X86_OP_FP:
            self._add("%f" % op.value.fp)
            return False

        elif op.type == X86_OP_MEM:
            mm = op.mem

            if not inv(mm.base) and mm.disp != 0 \
                and inv(mm.segment) and inv(mm.index):

                if (mm.base == X86_REG_RBP or mm.base == X86_REG_EBP) and \
                       self.var_name_exists(i, num_op):
                    self._variable(self.get_var_name(i, num_op))
                    return True
                elif mm.base == X86_REG_RIP or mm.base == X86_REG_EIP:
                    addr = i.address + i.size + mm.disp
                    self._add("*(")
                    if addr in self.binary.reverse_symbols:
                        self._symbol(addr)
                    else:
                        self._add(hex(addr))
                    self._add(")")
                    return True

            printed = False
            if show_deref:
                self._add("*(")

            if not inv(mm.base):
                self._add("%s" % i.reg_name(mm.base))
                printed = True

            elif not inv(mm.segment):
                self._add("%s" % i.reg_name(mm.segment))
                printed = True

            if not inv(mm.index):
                if printed:
                    self._add(" + ")
                if mm.scale == 1:
                    self._add("%s" % i.reg_name(mm.index))
                else:
                    self._add("(%s*%d)" % (i.reg_name(mm.index), mm.scale))
                printed = True

            if mm.disp != 0:
                sec_name, is_data = self.binary.is_address(mm.disp)
                if sec_name is not None:
                    if printed:
                        self._add(" + ")
                    if mm.disp in self.binary.reverse_symbols:
                        self._symbol(mm.disp)
                    else:
                        self._add(hex(mm.disp))
                else:
                    if printed:
                        if mm.disp < 0:
                            self._add(" - %d" % (-mm.disp))
                        else:
                            self._add(" + %d" % mm.disp)

            if show_deref:
                self._add(")")
            return True


    def _if_cond(self, jump_cond, fused_inst):
        if fused_inst is None:
            self._add(cond_symbol(jump_cond))
            if jump_cond in JMP_ADD_ZERO:
                self._add(" 0")
            return

        assignment = fused_inst.id in ASSIGNMENT_OPS

        if assignment:
            self._add("(")
        self._add("(")
        self._operand(fused_inst, 0)
        self._add(" ")

        if fused_inst.id == X86_INS_TEST:
            self._add(cond_symbol(jump_cond))
        elif assignment:
            self._add(inst_symbol(fused_inst))
            self._add(" ")
            self._operand(fused_inst, 1)
            self._add(") ")
            self._add(cond_symbol(jump_cond))
        else:
            self._add(cond_symbol(jump_cond))
            self._add(" ")
            self._operand(fused_inst, 1)

        if fused_inst.id == X86_INS_TEST or \
                (fused_inst.id != X86_INS_CMP and \
                 (jump_cond in JMP_ADD_ZERO or assignment)):
            self._add(" 0")

        self._add(")")


    def _asm_inst(self, i, tab=0, prefix=""):
        def get_inst_str():
            nonlocal i
            return "%s %s" % (i.mnemonic, i.op_str)

        if i.address in self.ctx.dis.previous_comments:
            for comm in self.ctx.dis.previous_comments[i.address]:
                self._tabs(tab)
                self._internal_comment("; %s" % comm)
                self._new_line()

        if prefix == "# ":
            if self.ctx.comments:
                if i.address in self.ctx.labels:
                    self._label(i.address, tab)
                    self._new_line()
                    self._tabs(tab)
                    self._comment(prefix)
                    self._address(i.address, normal_color=True)
                else:
                    self._tabs(tab)
                    self._comment(prefix)
                    self._address(i.address)
                self._bytes(i, True)
                self._comment(get_inst_str())
                self._new_line()
            return

        if i.address in self.ctx.all_fused_inst:
            return

        if self.is_symbol(i.address):
            self._tabs(tab)
            self._symbol(i.address)
            self._new_line()

        modified = self.__sub_asm_inst(i, tab, prefix)

        if i.address in self.ctx.dis.inline_comments:
            self._internal_comment(" ; %s" %
                    self.ctx.dis.inline_comments[i.address])

        if modified and self.ctx.comments:
            self._comment(" # %s" % get_inst_str())

        self._new_line()


    def _rep_begin(self, i, tab):
        if i.prefix[0] in REP_PREFIX:
            self._tabs(tab)
            self._keyword("while")
            # TODO: for 16 and 32 bits
            self._add(" (!rcx)) {")
            self._new_line()
            tab += 1
        return tab


    def _rep_end(self, i, tab):
        if i.prefix[0] in REP_PREFIX:
            self._new_line()
            self._label_or_address(i.address, tab)
            self._add("rcx--")
            self._new_line()
            if i.prefix[0] == X86_PREFIX_REPNE:
                self._tabs(tab)
                self._keyword("if")
                self._add(" (!Z) ")
                self._keyword("break")
                self._new_line()
            tab -= 1
            self._tabs(tab)
            self._add("}")


    def __sub_asm_inst(self, i, tab=0, prefix=""):
        def get_inst_str():
            nonlocal i
            return "%s %s" % (i.mnemonic, i.op_str)

        tab = self._rep_begin(i, tab)
        self._label_and_address(i.address, tab)
        self._bytes(i)

        if is_ret(i):
            self._retcall(get_inst_str())
            return False

        if is_call(i):
            self._retcall(i.mnemonic)
            self._add(" ")
            return self._operand(i, 0, hexa=True)

        # Here we can have conditional jump with the option --dump
        if is_jump(i):
            self._add(i.mnemonic + " ")
            if i.operands[0].type != X86_OP_IMM:
                self._operand(i, 0)
                if is_uncond_jump(i) and self.ctx.comments and not self.ctx.dump \
                        and not i.address in self.ctx.dis.jmptables:
                    self._comment(" # STOPPED")
                return False
            addr = i.operands[0].value.imm
            if addr in self.ctx.addr_color:
                self._label_or_address(addr, -1, False)
            else:
                self._add(hex(addr))
            return False


        modified = False

        if i.id in INST_CHECK:
            if (i.id == X86_INS_OR and i.operands[1].type == X86_OP_IMM and
                    i.operands[1].value.imm == -1):
                self._operand(i, 0)
                self._add(" = -1")

            elif (i.id == X86_INS_AND and i.operands[1].type == X86_OP_IMM and
                    i.operands[1].value.imm == 0):
                self._operand(i, 0)
                self._add(" = 0")

            elif (all(op.type == X86_OP_REG for op in i.operands) and
                    len(set(op.value.reg for op in i.operands)) == 1 and
                    i.id == X86_INS_XOR):
                self._operand(i, 0)
                self._add(" = 0")

            elif i.id == X86_INS_INC or i.id == X86_INS_DEC:
                self._operand(i, 0)
                self._add(inst_symbol(i))

            elif i.id == X86_INS_LEA:
                self._operand(i, 0)
                self._add(" = &(")
                self._operand(i, 1)
                self._add(")")

            elif i.id == X86_INS_MOVZX:
                self._operand(i, 0)
                self._add(" = (zero ext) ")
                self._operand(i, 1)

            elif i.id == X86_INS_IMUL:
                if len(i.operands) == 3:
                    self._operand(i, 0)
                    self._add(" = ")
                    self._operand(i, 1)
                    self._add(" " + inst_symbol(i).rstrip('=') + " ")
                    self._operand(i, 2)
                elif len(i.operands) == 2:
                    self._operand(i, 0)
                    self._add(" " + inst_symbol(i) + " ")
                    self._operand(i, 1)
                elif len(i.operands) == 1:
                    sz = i.operands[0].size
                    if sz == 1:
                        self._add("ax = al * ")
                    elif sz == 2:
                        self._add("dx:ax = ax * ")
                    elif sz == 4:
                        self._add("edx:eax = eax * ")
                    elif sz == 8:
                        self._add("rdx:rax = rax * ")
                    self._operand(i, 0)

            else:
                self._operand(i, 0)
                self._add(" " + inst_symbol(i) + " ")
                self._operand(i, 1)

            modified = True

        elif i.id == X86_INS_CDQE:
            self._add("rax = eax")
            modified = True

        elif i.id == X86_INS_IDIV:
            self._add('eax = edx:eax / ')
            self._operand(i, 0)
            self._add('; edx = edx:eax % ')
            self._operand(i, 0)
            modified = True

        elif i.id == X86_INS_MUL:
            lut = {1: ("al", "ax"), 2: ("ax", "dx:ax"), 4: ("eax", "edx:eax"),
                    8: ("rax", "rdx:rax")}
            src, dst = lut[i.operands[0].size]
            self._add('{0} = {1} * '.format(dst, src))
            self._operand(i, 0)
            modified = True

        elif i.id == X86_INS_NOT:
            self._operand(i, 0)
            self._add(' ^= -1')
            modified = True

        elif i.id in INST_SCAS:
            self._operand(i, 0)
            self._add(" cmp ")
            self._operand(i, 1)
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 1, show_deref=False)
            self._add(" += D")
            modified = True

        elif i.id in INST_STOS:
            self._operand(i, 0)
            self._add(" = ")
            self._operand(i, 1)
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 0, show_deref=False)
            self._add(" += D")
            modified = True

        elif i.id in INST_LODS:
            self._operand(i, 0)
            self._add(" = ")
            self._operand(i, 1)
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 1, show_deref=False)
            self._add(" += D")
            modified = True

        elif i.id in INST_CMPS:
            self._operand(i, 0)
            self._add(" cmp ")
            self._operand(i, 1)
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 0, show_deref=False)
            self._add(" += D")
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 1, show_deref=False)
            self._add("' += D")
            modified = True

        elif i.id in INST_MOVS:
            self._operand(i, 0)
            self._add(" = ")
            self._operand(i, 1)
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 0, show_deref=False)
            self._add(" += D")
            self._new_line()
            self._label_or_address(i.address, tab)
            self._operand(i, 1, show_deref=False)
            self._add(" += D")
            modified = True

        else:
            self._add("%s " % i.mnemonic)
            if len(i.operands) > 0:
                modified = self._operand(i, 0)
                k = 1
                while k < len(i.operands):
                    self._add(", ")
                    modified |= self._operand(i, k)
                    k += 1

        self._rep_end(i, tab)

        return modified
