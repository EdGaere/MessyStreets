# -*- coding: utf-8 -*-

"""
config.py: default settings for all machine learning models

base: datalake/mock/b.3/ml/config.py

edward | 2021-08-22 | Initial version
edward | 2021-11-28 | upgraded is_date model to datatype.ovr.date.2
edward | 2021-11-28 | upgraded is_numeric model to datatype.ovr.numeric.2
edward | 2022-02-11 | upgraded is_date model to datatype.ovr.date.3

"""

from copy import deepcopy
from os import path, environ
import sys

from babel import Locale

from serentec.exceptions import PathNotFound

# logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("Config(ML)")

class Config:

     def __init__(self, debug : bool = False):

          self.debug = debug

          # when making a prediction from a string that contains a character that was not present in the training data
          # replace that character with this one
          self.default_encoding_character = "?"

          # what to predict when there is no output available
          # specifically in generate11 with schemas
          self.null_target = "NULL"
     
          # detect virtual enviroment
          self.virtual_environment_name = path.basename(sys.prefix)

          if self.debug:
               module_logger.debug(f"virtual_environment_name : {self.virtual_environment_name}")

          # locate the path used for downloads
          # e.g for data downloaded from schema.org
          # NOTE: /local/home/gaeree for ETH GPU
          # NOTE: /home/ubuntu for lambda labs
          # NOTE: /root for runpod
          self.data_download_path = None
          self.data_download_paths = ['/home/edward/data'
                                   , '/Users/gaeree/data'
                                   , '/local/home/gaeree/data'
                                   , '/Users/edward/data'
                                   , '/Users/edwardgaere/data'
                                   , '/home/ubuntu/data'
                                   , '/root/data'
                                   , '/home/gaeree/data'
                                   ]

          # find the first available path
          for data_download_path in self.data_download_paths:
               if path.exists(data_download_path):
                    self.data_download_path = data_download_path
                    break

          if self.data_download_path is None:
               raise PathNotFound(f"None of the data paths could be found : {self.data_download_paths}")
          
          #module_logger.debug(f"data_download_path : {self.data_download_path}")

          self.schema_org_data_path = path.join(self.data_download_path, 'schemaorgtables')
          if not path.exists(self.schema_org_data_path):
               #raise PathNotFound(f"Path {self.schema_org_data_path} not found : {self.schema_org_data_path}")
               #module_logger.warning(f"Path {self.schema_org_data_path} not found : {self.schema_org_data_path}")
               pass

          self.dbpedia_data_path =  path.join(self.data_download_path, 'dbpedia')
          if not path.exists(self.dbpedia_data_path):
               #raise PathNotFound(f"Path {self.dbpedia_data_path} not found : {self.dbpedia_data_path}")
               #module_logger.warning(f"Path {self.dbpedia_data_path} not found : {self.dbpedia_data_path}")
               pass

          self.babel_data_path =  path.join(self.data_download_path, 'babel')
          if not path.exists(self.babel_data_path):
               #raise PathNotFound(f"Path {self.babel_data_path} not found : {self.babel_data_path}")
               #module_logger.warning(f"Path {self.babel_data_path} not found : {self.babel_data_path}")
               pass

          # faker.12: locales for faker library; not all locales are supported (e.g nn_NO)
          self.faker_locales = ["en_US", "en_GB", "de_DE", "de_CH", "fr_FR", "fr_CH", "sv_SE", "es_ES", "no_NO", "it_IT", "nl_NL", "pt_PT"]

          # mini10: from /serentec/ml/generators/dates/date/generate18.py
          self.mini10_locales = ["en_US", "en_GB", "de_DE", "fr_CH", "sv_SE", "es_ES", "nn_NO", "it_IT", "nl_NL", "pt_PT"]

          self.mini10_countries = [locale_name.split("_")[1] for locale_name in self.mini10_locales]


          # SAP List of locales and their dominant locales (60 locales = 71 elements from SAP website less 11 not recognised or causing problems in Babel)
          # src: https://help.sap.com/docs/SAP_BUSINESSOBJECTS_BUSINESS_INTELLIGENCE_PLATFORM/09382741061c40a989fae01e61d54202/46758c5e6e041014910aba7db0e91070.html?version=4.2.4&locale=en-US
          # Removed as causing problems in Babel: tn_ZA, syr_SY, mn_MN, kk_KZ, sq_AL, tr_TR, ru_RU, te_IN, xh_ZA, uk_UA, mk_MK, ta_IN
          self.sap_dominant_locales = ["af_ZA", "ar_SA", "hy_AM", "az_AZ", "eu_ES", "bn_IN", "bs_BA", "bg_BG", "ca_ES", "zh_TW", "zh_CN", "hr_HR", "cs_CZ"
          , "da_DK", "nl_NL", "en_US", "et_EE", "fo_FO", "fi_FI", "fr_FR", "gl_ES", "ka_GE", "de_DE", "el_GR", "gu_IN", "he_IL", "hi_IN", "hu_HU", "is_IS", "id_ID", "it_IT", "ja_JP", "kn_IN"
          , "kok_IN", "ko_KR", "lv_LV", "lt_LT",  "ms_MY", "ml_IN", "mt_MT", "mr_IN", "se_NO", "nb_NO", "nn_NO", "fa_IR", "pl_PL"
          , "pt_BR", "pa_IN", "ro_RO", "sr_BA", "sk_SK", "es_ES", "sw_KE", "sv_SE", "th_TH", "uz_UZ", "vi_VN", "cy_GB", "zu_ZA"
          ]

          # add de_CH so that we get the thousand separator for numbers
          # see /Dropbox/programming/python/babel/list_of_thousand_decimal_separator_pairs.py
          # edward | 2022-02-07
          self.faker_locales.append("de_CH")

          # create a standardised number inference, to generate targets that are all in the same format
          # and can be parsed by Python simply using d = float(s)
          # for example
          # -78 836 556,0959 -> -78836556.0959
          # '-7,884 10^7 -> -7.884E7
          self.standard_number_locale = Locale("en_US")
          # CRITICAL: number_symbols is a property, not a member value
          # so we need to load the data into the instance *before* the deepcopy operation
          # else we are the changing the base class and thus all instances of this locale
          # src: https://stackoverflow.com/questions/40154093/how-can-i-change-the-locale-thousands-separator-in-python-to-arabic-unicode-se
          self.standard_number_locale.number_symbols
          sys.setrecursionlimit(10000)
          self.standard_number_locale = deepcopy(self.standard_number_locale)
          self.standard_number_locale.number_symbols['group'] = "" # remove thousand separator (for this copy only)

          # inference models for production
          self.model_config_path = path.join( environ.get("PYTHONPATH"), "serentec/ml/lstm", "configs")
          self.model_path = path.join( environ.get("PYTHONPATH"), "serentec/ml/lstm", "models")

          # data generators
          self.generator_path = path.join( environ.get("PYTHONPATH"), "serentec/ml/generators")
          
          # nn_infer.py
          self.model_inference_sample_size = 50 # maximum number of unique values to input for LSTM model

          # edward | 2021-11-28 | upgraded is_date model to datatype.ovr.date.2
          # edward | 2022-02-11 | upgraded is_date model to datatype.ovr.date.3
          # NOTE: model used by InferDefFile(v2), IsColumnName
          #self.modelname_datatype_is_date = "datatype.ovr.date.1" # OVR is date
          #self.modelname_datatype_is_date = "datatype.ovr.date.2" # OVR is date
          self.modelname_datatype_is_date = "datatype.ovr.date.3" # OVR is date
          # BACKLOG: upgrade to datatype.ovr.date.4 once training is completed
          
          # edward | 2021-11-28 | upgraded is_numeric model to datatype.ovr.numeric.2
          # NOTE: model used by InferDefFile(v2), IsColumnName
          #self.modelname_datatype_is_numeric = "datatype.ovr.numeric.1" # OVR is numeric (float, int)
          self.modelname_datatype_is_numeric = "datatype.ovr.numeric.2" # OVR is numeric (float, int)
          # BACKLOG: upgrade to datatype.ovr.numeric.3 once training is completed
          

          # edward | 2021-12-22 | predict if string represents a time (OVR)
          # NOTE: model used by InferDefFile(v2), IsColumnName
          self.modelname_datatype_is_time = "datatype.ovr.time.1"
          

          # lstm_float_vs_int
          # One-versus-rest (OVR) datatype prediction, for type NUMERIC -> (INT, FLOAT).
          # Intended to run as a sub-model of is_numeric, that is once we have identified a number, we 
          # use this model to determine if number is integer or a float.
          self.modelname_datatype_float_vs_int = "datatype.ovr.float_vs_int.2"
          
          # date type: DATE, YEAR_WEEK, YEAR_MONTH, YEAR_QUARTER, DATETIME
          #self.modelname_date_model = "date.type.1"
          self.modelname_date_model = "date.type.2" # upgraded | edward | 2022-01-31
          # BACKLOG: upgrade to date.type.3 once training is completed

          # NER models (Named Entity Resolution) : IPV4, Person, Address, etc
          # NOTE: set to None to skip the model
          # BACKLOG: create enum

          self.ner_models = {
               "Person" : None # "ner.ovr.person.1"
               , "City" : None #"ner.ovr.city.2"
          }

          # date format inference; maps a date type to a parsing model
          # e.g date -> date.template2.2
          # list of models required: 'timestamp', 'date', 'year_week', 'year_month', 'year_quarter' 

          
          # TODO: get rid of this, replace with reasoner
          self.date_format_inference_models = {
                     "datetime" : "datetime.template2.3"
                     , "date" : "date.template2.3"
                     , "year_week" : "year_week.template2.2"
                     , "year_month" : "year_month.template2.2"
                     , "year_quarter" : "year_quarter.template2.2"
                     }

          # for lstm/inference/infer_datetime; models must be located in lstm/models
          # and must a concrete function must be been compiled
          # if no model is available, simply specify None

          # TODO: get rid of this, replace with reasoner
          self.datetime_inference_models = {
               "century" : "datetime.century.seq2seq.1"
               , "decade" : "datetime.decade.seq2seq.2"
               , "month" : "datetime.month.seq2seq.1"
               , "day" : "datetime.day.seq2seq.1"
               , "hour" : "datetime.hour.seq2seq.1"
               , "minute" : "datetime.minute.seq2seq.1"
               , "second" : "datetime.second.seq2seq.2"

          }

     
              

if __name__ == "__main__":

     def main():
          config = Config()

     main()