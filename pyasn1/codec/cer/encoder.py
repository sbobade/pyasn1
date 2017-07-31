#
# This file is part of pyasn1 software.
#
# Copyright (c) 2005-2017, Ilya Etingof <etingof@gmail.com>
# License: http://pyasn1.sf.net/license.html
#
from pyasn1.type import univ
from pyasn1.type import useful
from pyasn1.codec.ber import encoder
from pyasn1.compat.octets import str2octs, null
from pyasn1 import error

__all__ = ['encode']


class BooleanEncoder(encoder.IntegerEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if value == 0:
            substrate = (0,)
        else:
            substrate = (255,)
        return substrate, False, False


class BitStringEncoder(encoder.BitStringEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return encoder.BitStringEncoder.encodeValue(
            self, encodeFun, value, defMode, 1000
        )


class OctetStringEncoder(encoder.OctetStringEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return encoder.OctetStringEncoder.encodeValue(
            self, encodeFun, value, defMode, 1000
        )


class RealEncoder(encoder.RealEncoder):
    def _chooseEncBase(self, value):
        m, b, e = value
        return self._dropFloatingPoint(m, b, e)


# specialized GeneralStringEncoder here

class TimeEncoderMixIn(object):
    zchar, = str2octs('Z')
    pluschar, = str2octs('+')
    minuschar, = str2octs('-')
    commachar, = str2octs(',')
    minLength = 12
    maxLength = 19

    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        # Encoding constraints:
        # - minutes are mandatory, seconds are optional
        # - subseconds must NOT be zero
        # - no hanging fraction dot
        # - time in UTC (Z)
        # - only dot is allowed for fractions

        octets = value.asOctets()

        if not self.minLength < len(octets) < self.maxLength:
            raise error.PyAsn1Error('Length constraint violated: %r' % value)

        if self.pluschar in octets or self.minuschar in octets:
            raise error.PyAsn1Error('Must be UTC time: %r' % octets)

        if octets[-1] != self.zchar:
            raise error.PyAsn1Error('Missing "Z" time zone specifier: %r' % octets)

        if self.commachar in octets:
            raise error.PyAsn1Error('Comma in fractions disallowed: %r' % value)

        return encoder.OctetStringEncoder.encodeValue(
            self, encodeFun, value, defMode, 1000
        )


class GeneralizedTimeEncoder(TimeEncoderMixIn, OctetStringEncoder):
    minLength = 12
    maxLength = 19


class UTCTimeEncoder(TimeEncoderMixIn, encoder.OctetStringEncoder):
    minLength = 10
    maxLength = 14


class SetOfEncoder(encoder.SequenceOfEncoder):
    @staticmethod
    def _sortComponents(components):
        # sort by tags regardless of the Choice value (static sort)
        return sorted(components, key=lambda x: isinstance(x, univ.Choice) and x.minTagSet or x.tagSet)

    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        value.verifySizeSpec()
        substrate = null
        idx = len(value)
        # This is certainly a hack but how else do I distinguish SetOf
        # from Set if they have the same tags&constraints?
        if isinstance(value, univ.SequenceAndSetBase):
            # Set
            namedTypes = value.componentType
            comps = []
            compsMap = {}
            while idx > 0:
                idx -= 1
                if namedTypes:
                    if namedTypes[idx].isOptional and not value[idx].isValue:
                        continue
                    if namedTypes[idx].isDefaulted and value[idx] == namedTypes[idx].asn1Object:
                        continue

                comps.append(value[idx])
                compsMap[id(value[idx])] = namedTypes[idx].isOptional

            for comp in self._sortComponents(comps):
                substrate += encodeFun(comp, defMode, maxChunkSize, compsMap[id(comp)])
        else:
            # SetOf
            compSubs = []
            while idx > 0:
                idx -= 1
                compSubs.append(
                    encodeFun(value[idx], defMode, maxChunkSize)
                )
            compSubs.sort()  # perhaps padding's not needed
            substrate = null
            for compSub in compSubs:
                substrate += compSub
        return substrate, True, True


class SequenceEncoder(encoder.SequenceEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        value.verifySizeSpec()
        namedTypes = value.componentType
        substrate = null
        idx = len(value)
        while idx > 0:
            idx -= 1
            if namedTypes:
                if namedTypes[idx].isOptional and not value[idx].isValue:
                    continue
                if namedTypes[idx].isDefaulted and value[idx] == namedTypes[idx].asn1Object:
                    continue

            substrate = encodeFun(value[idx], defMode, maxChunkSize, namedTypes[idx].isOptional) + substrate

        return substrate, True, True

tagMap = encoder.tagMap.copy()
tagMap.update({
    univ.Boolean.tagSet: BooleanEncoder(),
    univ.BitString.tagSet: BitStringEncoder(),
    univ.OctetString.tagSet: OctetStringEncoder(),
    univ.Real.tagSet: RealEncoder(),
    useful.GeneralizedTime.tagSet: GeneralizedTimeEncoder(),
    useful.UTCTime.tagSet: UTCTimeEncoder(),
    # Sequence & Set have same tags as SequenceOf & SetOf
    univ.SetOf.tagSet: SetOfEncoder(),
    univ.Sequence.typeId: SequenceEncoder()
})

typeMap = encoder.typeMap.copy()
typeMap.update({
    univ.Boolean.typeId: BooleanEncoder(),
    univ.BitString.typeId: BitStringEncoder(),
    univ.OctetString.typeId: OctetStringEncoder(),
    univ.Real.typeId: RealEncoder(),
    useful.GeneralizedTime.typeId: GeneralizedTimeEncoder(),
    useful.UTCTime.typeId: UTCTimeEncoder(),
    # Sequence & Set have same tags as SequenceOf & SetOf
    univ.Set.typeId: SetOfEncoder(),
    univ.SetOf.typeId: SetOfEncoder(),
    univ.Sequence.typeId: SequenceEncoder()
})


class Encoder(encoder.Encoder):

    def __call__(self, value, defMode=False, maxChunkSize=0, isOptional=False):
        return encoder.Encoder.__call__(self, value, defMode, maxChunkSize, isOptional)


#: Turns ASN.1 object into CER octet stream.
#:
#: Takes any ASN.1 object (e.g. :py:class:`~pyasn1.type.base.PyAsn1Item` derivative)
#: walks all its components recursively and produces a CER octet stream.
#:
#: Parameters
#: ----------
#  value: any pyasn1 object (e.g. :py:class:`~pyasn1.type.base.PyAsn1Item` derivative)
#:     A pyasn1 object to encode
#:
#: defMode: :py:class:`bool`
#:     If `False`, produces indefinite length encoding
#:
#: maxChunkSize: :py:class:`int`
#:     Maximum chunk size in chunked encoding mode (0 denotes unlimited chunk size)
#:
#: Returns
#: -------
#: : :py:class:`bytes` (Python 3) or :py:class:`str` (Python 2)
#:     Given ASN.1 object encoded into BER octetstream
#:
#: Raises
#: ------
#: : :py:class:`pyasn1.error.PyAsn1Error`
#:     On encoding errors
encode = Encoder(tagMap, typeMap)

# EncoderFactory queries class instance and builds a map of tags -> encoders
