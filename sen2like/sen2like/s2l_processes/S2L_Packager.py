#! /usr/bin/env python
# -*- coding: utf-8 -*-
# V. Debaecker (TPZ-F) 2018

import datetime as dt
import logging
import os
import shutil
from core import S2L_config
from core.S2L_tools import quicklook
from core.image_file import S2L_ImageFile
from core.products.product import S2L_Product
from grids import mgrs_framing
from s2l_processes.S2L_Process import S2L_Process

log = logging.getLogger("Sen2Like")


class S2L_Packager(S2L_Process):
    images = {}
    out_variables = ['images']

    @staticmethod
    def base_path(product):
        relative_orbit = S2L_config.config.get('relative_orbit')
        acqdate = dt.datetime.strftime(product.acqdate, '%Y%m%d')
        tilecode = product.mtl.mgrs
        if tilecode.startswith('T'):
            tilecode = tilecode[1:]
        return "_".join(['L2F', tilecode, acqdate, product.sensor_name, 'R{:0>3}'.format(relative_orbit)]), tilecode

    def process(self, product: S2L_Product, image: S2L_ImageFile, band: str) -> S2L_ImageFile:
        """
        Write final product in the archive directory
        'archive_dir' is defined in config.ini file
        Naming convention from Design Document
        :param product: instance of S2L_Product class
        :param image: input instance of S2L_ImageFile class
        :param band: band being processed
        :return: outpu  t instance of instance of S2L_ImageFile class
        """

        # TODO : add production date?
        # TODO : change L8 band numbers to S2 numbers convention?

        # /data/HLS_DATA/Archive/Site_Name/TILE_ID/S2L_DATEACQ_DATEPROD_SENSOR/S2L_DATEACQ_DATEPROD_SENSOR
        res = image.xRes
        outdir, tilecode = self.base_path(product)
        outfile = "_".join([outdir, band, '{}m'.format(int(res))]) + '.TIF'
        tsdir = os.path.join(S2L_config.config.get('archive_dir'), tilecode)  # ts = temporal series
        newpath = os.path.join(tsdir, outdir, outfile)

        log.debug('New: ' + newpath)
        image.write(creation_options=['COMPRESS=LZW'], filepath=newpath)

        # declare output internally
        self.images[band] = image.filepath
        # declare output in config file
        S2L_config.config.set('imageout_dir', image.dirpath)
        S2L_config.config.set('imageout_' + band, image.filename)

        if S2L_config.config.getboolean('hlsplus'):
            res = 30
            outfile_30m = "_".join([outdir, band, '{}m'.format(int(res))]) + '.TIF'
            newpath_30m = os.path.join(tsdir, outdir, outfile_30m)
            if product.sensor == 'S2':
                # create 30m band as well
                # resampling
                log.info('Resampling to 30m: Start...')
                image_30m = mgrs_framing.resample(S2L_ImageFile(newpath), res, newpath_30m)
                image_30m.write(creation_options=['COMPRESS=LZW'], DCmode=True)  # digital count
                log.info('Resampling to 30m: End')

            if product.sensor in ('L8', 'L9') and band in product.image30m:
                # copy 30m band as well
                # write
                product.image30m[band].write(creation_options=['COMPRESS=LZW'], filepath=newpath_30m)
                del product.image30m[band]

        return image

    def postprocess(self, product: S2L_Product):
        """
        Copy auxiliary files in the final output like mask, angle files
        Input product metadata file is also copied.
        :param pd: instance of S2L_Product class
        """

        # output directory
        outdir, tilecode = self.base_path(product)
        tsdir = os.path.join(S2L_config.config.get('archive_dir'), tilecode)  # ts = temporal series

        # copy MTL files in final product
        outfile = os.path.basename(product.mtl.mtl_file_name)
        shutil.copyfile(product.mtl.mtl_file_name, os.path.join(tsdir, outdir, outfile))
        if product.mtl.tile_metadata:
            outfile = os.path.basename(product.mtl.tile_metadata)
            shutil.copyfile(product.mtl.tile_metadata, os.path.join(tsdir, outdir, outfile))

        # copy angles file
        outfile = "_".join([outdir, 'ANG']) + '.TIF'
        shutil.copyfile(product.angles_file, os.path.join(tsdir, outdir, outfile))

        # copy valid pixel mask
        outfile = "_".join([outdir, 'MSK']) + '.TIF'
        shutil.copyfile(product.mask_filename, os.path.join(tsdir, outdir, outfile))

        # QI directory
        qipath = os.path.join(tsdir, 'QI')
        if not os.path.exists(qipath):
            os.makedirs(qipath)

        # save config file in QI
        cfgname = "_".join([outdir, 'INFO']) + '.cfg'
        cfgpath = os.path.join(tsdir, 'QI', cfgname)
        S2L_config.config.savetofile(os.path.join(S2L_config.config.get('wd'), product.name, cfgpath))

        # save correl file in QI
        if os.path.exists(os.path.join(S2L_config.config.get('wd'), product.name, 'correl_res.txt')):
            corrname = "_".join([outdir, 'CORREL']) + '.csv'
            corrpath = os.path.join(tsdir, 'QI', corrname)
            shutil.copy(os.path.join(S2L_config.config.get('wd'), product.name, 'correl_res.txt'), corrpath)

        if len(self.images.keys()) > 1:
            # true color QL
            band_list = ["B04", "B03", "B02"]
            qlname = "_".join([outdir, 'QL', 'B432']) + '.jpg'
            qlpath = os.path.join(tsdir, 'QI', 'QL_B432', qlname)
            quicklook(product, self.images, band_list, qlpath, S2L_config.config.get(
                "quicklook_jpeg_quality", 95), offset=int(S2L_config.config.get('offset')))

            # false color QL
            band_list = ["B12", "B11", "B8A"]
            qlname = "_".join([outdir, 'QL', 'B12118A']) + '.jpg'
            qlpath = os.path.join(tsdir, 'QI', 'QL_B12118A', qlname)
            quicklook(product, self.images, band_list, qlpath, S2L_config.config.get(
                "quicklook_jpeg_quality", 95), offset=int(S2L_config.config.get('offset')))
        else:
            # grayscale QL
            band_list = list(self.images.keys())
            qlname = "_".join([outdir, 'QL', band_list[0]]) + '.jpg'
            qlpath = os.path.join(tsdir, 'QI', f'QL_{band_list[0]}', qlname)
            quicklook(product, self.images, band_list, qlpath, S2L_config.config.get(
                "quicklook_jpeg_quality", 95), offset=int(S2L_config.config.get('offset')))

        # Clear images as packager is the last process
        self.images.clear()
